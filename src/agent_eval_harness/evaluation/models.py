"""Data models for synthetic evaluation cases, check results, and evaluation summaries."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_eval_harness.contracts.base import (
    CURRENT_SCHEMA_VERSION,
    StrictBaseModel,
    SupportedSchemaVersion,
)
from agent_eval_harness.contracts.handoff import OutreachChannel, OutreachTone
from agent_eval_harness.contracts.lead import QualificationStatus
from agent_eval_harness.contracts.lead_input import LeadInput
from agent_eval_harness.coordinator import CoordinatorStatus, OutreachConfig
from agent_eval_harness.evaluation.rubric import RubricDimension


class CheckSeverity(StrEnum):
    """Severity classification for deterministic evaluation checks.

    CRITICAL_BLOCKING: Guardrail or integrity violations that fail the evaluation
                       run independently, even if aggregate scores are high.
    WARNING: Non-blocking diagnostic observations or soft heuristic deviations.
    """

    CRITICAL_BLOCKING = "CRITICAL_BLOCKING"
    WARNING = "WARNING"


class ExpectedAssertions(StrictBaseModel):
    """Explicit deterministic assertions expected for an evaluation case."""

    expected_lifecycle_status: CoordinatorStatus = Field(..., strict=False)
    expected_qualification_status: QualificationStatus | None = Field(default=None, strict=False)
    min_fit_score: int | None = Field(default=None, ge=0, le=100)
    max_fit_score: int | None = Field(default=None, ge=0, le=100)
    forbidden_terms: list[str] = Field(
        default_factory=list,
        description="Terms that must NOT appear anywhere in the generated draft.",
    )
    required_terms: list[str] = Field(
        default_factory=list,
        description="Terms that MUST appear in the generated draft body or subject.",
    )
    max_word_count: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Explicit ceiling on the draft body word count.",
    )


class EvaluationCase(StrictBaseModel):
    """A versioned synthetic evaluation test case.

    Contains synthetic prospect data, workflow configuration, and expected
    deterministic assertions. Strictly fictional/synthetic with zero real-world data.
    """

    case_id: str = Field(..., min_length=1, max_length=64, pattern=r"^CASE-\d{3,4}$")
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=5, max_length=500)
    lead_input: LeadInput = Field(...)
    outreach_config: OutreachConfig = Field(
        default_factory=lambda: OutreachConfig(
            channel=OutreachChannel.EMAIL,
            target_persona="VP of Engineering",
            tone_preference=OutreachTone.PROFESSIONAL,
            max_words=150,
            constraints=[],
        )
    )
    expected: ExpectedAssertions = Field(...)
    is_synthetic: Literal[True] = Field(
        default=True,
        description="Invariant marker ensuring case contains strictly synthetic data.",
    )
    dataset_version: SupportedSchemaVersion = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="SemVer version of the dataset schema.",
    )


class CheckResult(BaseModel):
    """Result of an individual deterministic assertion check."""

    model_config = ConfigDict(extra="forbid", strict=True)

    check_name: str = Field(..., min_length=1)
    severity: CheckSeverity = Field(..., strict=False)
    passed: bool
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class DimensionScore(StrictBaseModel):
    """Score and required diagnostic rationale for a single rubric dimension."""

    dimension: RubricDimension = Field(..., strict=False)
    score: int = Field(..., ge=1, le=4, description="Discrete ordinal score on 1-4 scale")
    rationale: str = Field(
        ...,
        min_length=10,
        max_length=1500,
        description="Grounded justification citing specific evaluated text",
    )


class RawJudgeResponse(StrictBaseModel):
    """Raw JSON schema expected from the judge LLM completion.

    Contains only dimension scores. Excludes overall score and pass/fail flags to
    prevent LLM self-contradiction.
    """

    scores: list[DimensionScore] = Field(
        ..., description="Exactly 3 scores, one for each RubricDimension"
    )

    @model_validator(mode="after")
    def validate_exact_dimensions(self) -> "RawJudgeResponse":
        expected_dimensions = set(RubricDimension)
        if len(self.scores) != len(expected_dimensions):
            raise ValueError(
                f"Expected exactly {len(expected_dimensions)} dimension scores, "
                f"got {len(self.scores)}"
            )
        dimensions_present = [s.dimension for s in self.scores]
        if set(dimensions_present) != expected_dimensions:
            missing = expected_dimensions - set(dimensions_present)
            duplicates = [d for d in dimensions_present if dimensions_present.count(d) > 1]
            raise ValueError(
                f"Dimension mismatch. Missing: {missing}, Duplicates: {set(duplicates)}"
            )
        return self


class JudgeStatus(StrEnum):
    """Explicit semantic evaluation outcomes separating quality from errors."""

    COMPLETED_PASS = "COMPLETED_PASS"
    COMPLETED_FAIL = "COMPLETED_FAIL"
    INCONCLUSIVE_OUTPUT = "INCONCLUSIVE_OUTPUT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    SKIPPED_NON_APPLICABLE = "SKIPPED_NON_APPLICABLE"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"


class JudgeVerdict(StrictBaseModel):
    """Structured result of a semantic judge evaluation."""

    rubric_version: SupportedSchemaVersion = CURRENT_SCHEMA_VERSION
    model_identifier: str = Field(..., min_length=1)
    status: JudgeStatus = Field(..., strict=False)
    scores: list[DimensionScore] = Field(default_factory=list)
    error_category: str | None = None
    error_message: str | None = None

    @property
    def overall_score(self) -> float | None:
        """Deterministic arithmetic mean of dimension scores (rounded to 2 decimal places)."""
        if not self.scores:
            return None
        return round(sum(s.score for s in self.scores) / len(self.scores), 2)

    @property
    def passed(self) -> bool | None:
        """Whether the semantic evaluation completed and passed all rubric criteria.

        Returns:
            True: Semantic evaluation was executed and passed all rubric criteria
                  (COMPLETED_PASS).
            False: Semantic evaluation was executed and failed rubric criteria
                   (COMPLETED_FAIL), or produced malformed/invalid output (INCONCLUSIVE_OUTPUT),
                   or encountered an adapter error (EXECUTION_ERROR),
                   or workflow coordinator failed (WORKFLOW_FAILED).
            None: Semantic evaluation was not applicable because the workflow legitimately
                  skipped outreach drafting (SKIPPED_NON_APPLICABLE). No semantic quality
                  evaluation occurred.
        """
        if self.status == JudgeStatus.COMPLETED_PASS:
            return True
        if self.status == JudgeStatus.SKIPPED_NON_APPLICABLE:
            return None
        return False

    @model_validator(mode="after")
    def validate_verdict_invariants(self) -> "JudgeVerdict":
        expected_dimensions = set(RubricDimension)

        if self.status in (JudgeStatus.COMPLETED_PASS, JudgeStatus.COMPLETED_FAIL):
            if self.error_category is not None or self.error_message is not None:
                raise ValueError(f"{self.status} must not have error fields populated")

            if len(self.scores) != len(expected_dimensions):
                raise ValueError(
                    f"{self.status} requires exactly {len(expected_dimensions)} "
                    f"dimension scores, got {len(self.scores)}"
                )
            dimensions_present = [s.dimension for s in self.scores]
            if set(dimensions_present) != expected_dimensions:
                missing = expected_dimensions - set(dimensions_present)
                duplicates = [d for d in dimensions_present if dimensions_present.count(d) > 1]
                raise ValueError(
                    f"{self.status} dimension mismatch. "
                    f"Missing: {missing}, Duplicates: {set(duplicates)}"
                )

            passes_policy = all(s.score >= 3 for s in self.scores)
            if self.status == JudgeStatus.COMPLETED_PASS and not passes_policy:
                raise ValueError("COMPLETED_PASS requires all dimension scores >= 3")
            if self.status == JudgeStatus.COMPLETED_FAIL and passes_policy:
                raise ValueError("COMPLETED_FAIL requires at least one dimension score < 3")

        elif self.status in (
            JudgeStatus.INCONCLUSIVE_OUTPUT,
            JudgeStatus.EXECUTION_ERROR,
            JudgeStatus.WORKFLOW_FAILED,
        ):
            if self.scores:
                raise ValueError(f"{self.status} must not have scores populated")
            if self.error_category is None or self.error_message is None:
                raise ValueError(f"{self.status} requires error_category and error_message")

        else:  # JudgeStatus.SKIPPED_NON_APPLICABLE
            if self.scores:
                raise ValueError("SKIPPED_NON_APPLICABLE must not have scores populated")
            if self.error_category is not None or self.error_message is not None:
                raise ValueError("SKIPPED_NON_APPLICABLE must not have error fields populated")

        return self


class CaseEvaluationResult(BaseModel):
    """Aggregated evaluation outcome for a single evaluation case."""

    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    passed: bool
    has_critical_failure: bool
    execution_status: CoordinatorStatus = Field(..., strict=False)
    checks: list[CheckResult] = Field(default_factory=list)
    judge_verdict: JudgeVerdict | None = None


class DatasetEvaluationSummary(BaseModel):
    """Summary metrics and per-case results for a dataset evaluation run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    dataset_version: str
    total_cases: int = Field(..., ge=0)
    passed_cases: int = Field(..., ge=0)
    failed_cases: int = Field(..., ge=0)
    critical_failures: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    case_results: list[CaseEvaluationResult] = Field(default_factory=list)
