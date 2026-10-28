"""Baseline record contracts, canonical hashing, regression taxonomy, and comparison policy.

Enforces strict Pydantic v2 schemas for evaluation baselines and provides deterministic
regression comparison separating critical deterministic guardrails from semantic shifts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from agent_eval_harness.contracts.base import (
    CURRENT_SCHEMA_VERSION,
    StrictBaseModel,
    SupportedSchemaVersion,
)
from agent_eval_harness.coordinator import CoordinatorStatus
from agent_eval_harness.evaluation.models import CaseEvaluationResult, EvaluationCase, JudgeStatus
from agent_eval_harness.exceptions import BaselineIncompatibleError, BaselineUnavailableError


def compute_dataset_hash(dataset: Sequence[EvaluationCase] | Path | str) -> str:
    """Compute a canonical, deterministic SHA-256 hash of evaluation dataset content.

    Ensures line-ending, formatting, and key-order invariance by normalizing case payloads
    into a canonical JSON representation sorted by case_id.

    Args:
        dataset: A sequence of validated EvaluationCase models, or a path to a dataset JSON file.

    Returns:
        A hash string formatted as 'sha256:<64-char-hex>'.
    """
    cases_to_hash: list[dict[str, Any]] = []

    if isinstance(dataset, (Path, str)):
        path = Path(dataset)
        content = path.read_text(encoding="utf-8")
        raw_list = json.loads(content)
        if not isinstance(raw_list, list):
            raise ValueError(f"Dataset root must be a list, got {type(raw_list).__name__}")
        for item in raw_list:
            case = EvaluationCase.model_validate(item)
            cases_to_hash.append(case.model_dump(mode="json"))
    else:
        for case in dataset:
            cases_to_hash.append(case.model_dump(mode="json"))

    # Sort cases deterministically by case_id
    cases_to_hash.sort(key=lambda c: str(c.get("case_id", "")))

    # Produce canonical minified JSON with sorted keys
    canonical_json = json.dumps(
        cases_to_hash,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class RunMetadata(StrictBaseModel):
    """Execution metadata capturing reproducibility parameters of an evaluation run."""

    schema_version: SupportedSchemaVersion = CURRENT_SCHEMA_VERSION
    timestamp: datetime = Field(
        ...,
        strict=False,
        description="UTC timestamp of the evaluation run.",
    )
    commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA; None for uncommitted local runs.",
    )
    dataset_version: str = Field(..., min_length=1)
    dataset_hash: str = Field(..., min_length=1)
    rubric_version: str = Field(..., min_length=1)
    execution_mode: Literal["replay", "live"] = "replay"
    model_id: str | None = Field(
        default=None,
        description="Provider model ID; prohibited from specifying real LLM in replay mode.",
    )

    @model_validator(mode="after")
    def validate_metadata_invariants(self) -> RunMetadata:
        if self.execution_mode == "replay":
            if self.model_id is not None and self.model_id != "offline-replay":
                raise ValueError(
                    f"Replay execution mode must have model_id as None or 'offline-replay', "
                    f"got '{self.model_id}'."
                )
        elif self.execution_mode == "live" and (not self.model_id or not self.model_id.strip()):
            raise ValueError("Live execution mode requires a non-empty model_id.")
        return self


class BaselineRecord(StrictBaseModel):
    """Immutable, versioned baseline record representing an approved evaluation run."""

    schema_version: SupportedSchemaVersion = CURRENT_SCHEMA_VERSION
    metadata: RunMetadata
    total_cases: int = Field(..., ge=0)
    pass_count: int = Field(..., ge=0)
    fail_count: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    case_results: dict[str, CaseEvaluationResult] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_baseline_invariants(self) -> BaselineRecord:
        if self.total_cases != len(self.case_results):
            raise ValueError(
                f"total_cases ({self.total_cases}) does not match "
                f"number of case_results ({len(self.case_results)})"
            )
        if self.pass_count + self.fail_count != self.total_cases:
            raise ValueError(
                f"pass_count ({self.pass_count}) + fail_count ({self.fail_count}) "
                f"must equal total_cases ({self.total_cases})"
            )

        actual_passed = sum(1 for r in self.case_results.values() if r.passed)
        if actual_passed != self.pass_count:
            raise ValueError(
                f"pass_count ({self.pass_count}) does not match actual count of "
                f"passing cases in case_results ({actual_passed})"
            )

        expected_rate = (
            round(self.pass_count / self.total_cases, 4) if self.total_cases > 0 else 0.0
        )
        if abs(self.pass_rate - expected_rate) > 1e-4:
            raise ValueError(
                f"pass_rate ({self.pass_rate}) does not match calculated rate ({expected_rate})"
            )

        for case_id, res in self.case_results.items():
            if case_id != res.case_id:
                raise ValueError(
                    f"case_results key '{case_id}' does not match "
                    f"CaseEvaluationResult.case_id '{res.case_id}'"
                )

        return self


class BaselineComparisonStatus(StrEnum):
    """Outcome taxonomy for baseline comparison."""

    COMPARABLE = "comparable"
    INCOMPATIBLE = "incompatible"
    BASELINE_UNAVAILABLE = "baseline_unavailable"


class BaselineComparisonResult(StrictBaseModel):
    """Detailed structured report comparing current evaluation run against reference baseline."""

    status: BaselineComparisonStatus
    is_compatible: bool
    incompatibility_reasons: list[str] = Field(default_factory=list)
    has_regressions: bool = False
    critical_deterministic_regressions: list[str] = Field(default_factory=list)
    semantic_regressions: list[str] = Field(default_factory=list)
    regressed_cases: list[str] = Field(default_factory=list)
    improved_cases: list[str] = Field(default_factory=list)
    unchanged_cases: list[str] = Field(default_factory=list)
    missing_in_current: list[str] = Field(default_factory=list)
    missing_in_baseline: list[str] = Field(default_factory=list)
    score_deltas: dict[str, dict[str, float]] = Field(default_factory=dict)
    summary: str = ""


def compare_against_baseline(
    current: BaselineRecord,
    baseline: BaselineRecord | None,
    strict: bool = False,
) -> BaselineComparisonResult:
    """Compare current evaluation results against reference baseline.

    Args:
        current: The current evaluation run record.
        baseline: The reference baseline record, or None if unavailable.
        strict: If True, raises BaselineUnavailableError when baseline is None,
                or BaselineIncompatibleError when compatibility check fails,
                and treats missing cases in current as regressions.

    Returns:
        Structured BaselineComparisonResult.
    """
    if baseline is None:
        if strict:
            raise BaselineUnavailableError(
                "Baseline comparison failed: No reference baseline record was provided."
            )
        return BaselineComparisonResult(
            status=BaselineComparisonStatus.BASELINE_UNAVAILABLE,
            is_compatible=False,
            summary="Baseline comparison skipped: Reference baseline record is unavailable.",
        )

    # 1. Compatibility verification
    reasons: list[str] = []
    if current.metadata.dataset_hash != baseline.metadata.dataset_hash:
        reasons.append(
            f"Dataset hash mismatch: current='{current.metadata.dataset_hash}', "
            f"baseline='{baseline.metadata.dataset_hash}'"
        )
    if current.metadata.schema_version != baseline.metadata.schema_version:
        reasons.append(
            f"Schema version mismatch: current='{current.metadata.schema_version}', "
            f"baseline='{baseline.metadata.schema_version}'"
        )
    if current.metadata.rubric_version != baseline.metadata.rubric_version:
        reasons.append(
            f"Rubric version mismatch: current='{current.metadata.rubric_version}', "
            f"baseline='{baseline.metadata.rubric_version}'"
        )
    if current.metadata.execution_mode != baseline.metadata.execution_mode:
        reasons.append(
            f"Execution mode mismatch: current='{current.metadata.execution_mode}', "
            f"baseline='{baseline.metadata.execution_mode}'"
        )

    if reasons:
        if strict:
            raise BaselineIncompatibleError(
                f"Baseline comparison failed due to incompatibilities: {'; '.join(reasons)}"
            )
        return BaselineComparisonResult(
            status=BaselineComparisonStatus.INCOMPATIBLE,
            is_compatible=False,
            incompatibility_reasons=reasons,
            summary="Baseline comparison incompatible:\n" + "\n".join(f"- {r}" for r in reasons),
        )

    # 2. Detailed case-by-case comparison
    current_ids = set(current.case_results.keys())
    baseline_ids = set(baseline.case_results.keys())

    missing_in_current = sorted(baseline_ids - current_ids)
    missing_in_baseline = sorted(current_ids - baseline_ids)
    common_ids = sorted(current_ids & baseline_ids)

    critical_deterministic_regressions: list[str] = []
    semantic_regressions: list[str] = []
    regressed_cases: list[str] = []
    improved_cases: list[str] = []
    unchanged_cases: list[str] = []
    score_deltas: dict[str, dict[str, float]] = {}

    for cid in common_ids:
        b_case = baseline.case_results[cid]
        c_case = current.case_results[cid]

        # Check critical deterministic regression
        has_new_crit_failure = not b_case.has_critical_failure and c_case.has_critical_failure
        has_new_coord_failure = (
            b_case.execution_status != CoordinatorStatus.FAILED
            and c_case.execution_status == CoordinatorStatus.FAILED
        )
        if has_new_crit_failure or has_new_coord_failure:
            critical_deterministic_regressions.append(cid)

        # Check semantic regression
        if b_case.judge_verdict is not None and c_case.judge_verdict is not None:
            # Semantic status regressed from pass
            if (
                b_case.judge_verdict.status == JudgeStatus.COMPLETED_PASS
                and c_case.judge_verdict.status != JudgeStatus.COMPLETED_PASS
            ):
                semantic_regressions.append(cid)

            # Calculate dimension score deltas
            deltas: dict[str, float] = {}
            b_score_map = {s.dimension: s.score for s in b_case.judge_verdict.scores}
            for c_score in c_case.judge_verdict.scores:
                if c_score.dimension in b_score_map:
                    diff = round(float(c_score.score - b_score_map[c_score.dimension]), 2)
                    deltas[c_score.dimension.value] = diff
                    # Dimension dropped below pass threshold
                    if (
                        b_score_map[c_score.dimension] >= 3
                        and c_score.score < 3
                        and cid not in semantic_regressions
                    ):
                        semantic_regressions.append(cid)
            if deltas:
                score_deltas[cid] = deltas

        # Check overall pass/fail status
        if b_case.passed and not c_case.passed:
            regressed_cases.append(cid)
        elif not b_case.passed and c_case.passed:
            improved_cases.append(cid)
        else:
            unchanged_cases.append(cid)

    # Determine regression flag
    has_regressions = bool(
        critical_deterministic_regressions
        or semantic_regressions
        or regressed_cases
        or (strict and missing_in_current)
    )

    # Format human-readable markdown summary
    base_summary = f"{baseline.pass_rate * 100:.1f}% ({baseline.pass_count}/{baseline.total_cases})"
    curr_summary = f"{current.pass_rate * 100:.1f}% ({current.pass_count}/{current.total_cases})"
    summary_lines = [
        "### Baseline Comparison Report",
        f"- **Status:** {BaselineComparisonStatus.COMPARABLE.value.upper()}",
        f"- **Reference Baseline Pass Rate:** {base_summary}",
        f"- **Current Run Pass Rate:** {curr_summary}",
        f"- **Regressions Detected:** {'YES (FAIL)' if has_regressions else 'NO (PASS)'}",
        f"- **Critical Deterministic Regressions:** {len(critical_deterministic_regressions)}",
        f"- **Semantic Regressions:** {len(semantic_regressions)}",
        f"- **Net Regressed Cases:** {len(regressed_cases)}",
        f"- **Net Improved Cases:** {len(improved_cases)}",
        f"- **Unchanged Cases:** {len(unchanged_cases)}",
    ]

    if missing_in_current:
        summary_lines.append(f"- **Missing in Current Run:** {', '.join(missing_in_current)}")
    if missing_in_baseline:
        summary_lines.append(f"- **New in Current Run:** {', '.join(missing_in_baseline)}")

    if critical_deterministic_regressions:
        summary_lines.append("\n**Critical Deterministic Regressions:**")
        for cid in critical_deterministic_regressions:
            summary_lines.append(f"- `{cid}`: Triggered critical guardrail or coordinator failure")

    if semantic_regressions:
        summary_lines.append("\n**Semantic Regressions:**")
        for cid in semantic_regressions:
            summary_lines.append(f"- `{cid}`: Semantic judge score or verdict regressed")

    return BaselineComparisonResult(
        status=BaselineComparisonStatus.COMPARABLE,
        is_compatible=True,
        has_regressions=has_regressions,
        critical_deterministic_regressions=critical_deterministic_regressions,
        semantic_regressions=semantic_regressions,
        regressed_cases=regressed_cases,
        improved_cases=improved_cases,
        unchanged_cases=unchanged_cases,
        missing_in_current=missing_in_current,
        missing_in_baseline=missing_in_baseline,
        score_deltas=score_deltas,
        summary="\n".join(summary_lines),
    )
