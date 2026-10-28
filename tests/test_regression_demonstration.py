"""Regression demonstrations and comparison CLI verification tests.

Demonstrates that deliberate violations (planted secret leakage, word count ceiling
breaches, semantic score drops, and coordinator failures) trigger unambiguous failures,
and verifies deterministic CLI exit codes (0, 1, 2, 3, 4).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agent_eval_harness.contracts import (
    LeadQualificationResult,
    OutreachChannel,
    OutreachDraftResult,
    OutreachHandoff,
)
from agent_eval_harness.coordinator import CoordinatorResult, CoordinatorStatus
from agent_eval_harness.evaluation import (
    CheckResult,
    CheckSeverity,
    load_dataset,
)
from agent_eval_harness.evaluation.baseline import (
    BaselineRecord,
    RunMetadata,
    compare_against_baseline,
    compute_dataset_hash,
)
from agent_eval_harness.evaluation.checks import (
    check_forbidden_leakage,
    check_word_count_ceiling,
)
from agent_eval_harness.evaluation.compare_cli import main as cli_main
from agent_eval_harness.evaluation.dataset import DEFAULT_DATASET_PATH
from agent_eval_harness.evaluation.models import (
    CaseEvaluationResult,
    DimensionScore,
    JudgeStatus,
    JudgeVerdict,
)
from agent_eval_harness.evaluation.rubric import RubricDimension


@pytest.fixture
def dataset_hash() -> str:
    return compute_dataset_hash(DEFAULT_DATASET_PATH)


@pytest.fixture
def base_metadata(dataset_hash: str) -> RunMetadata:
    return RunMetadata(
        schema_version="1.0.0",
        timestamp=datetime.now(UTC),
        commit_sha=None,
        dataset_version="1.0.0",
        dataset_hash=dataset_hash,
        rubric_version="1.0.0",
        execution_mode="replay",
        model_id=None,
    )


def _build_valid_case_result(
    case_id: str = "CASE-001",
    score: int = 4,
    has_critical_failure: bool = False,
    execution_status: CoordinatorStatus = CoordinatorStatus.COMPLETED,
    checks: list[CheckResult] | None = None,
) -> CaseEvaluationResult:
    """Builds a valid case evaluation result for demonstration purposes."""
    scores = [
        DimensionScore(dimension=dim, score=score, rationale="Demonstration rationale.")
        for dim in RubricDimension
    ]
    status = JudgeStatus.COMPLETED_PASS if score >= 3 else JudgeStatus.COMPLETED_FAIL
    judge_verdict = JudgeVerdict(
        rubric_version="1.0.0",
        model_identifier="test-evaluator",
        status=status,
        scores=scores,
    )
    return CaseEvaluationResult(
        case_id=case_id,
        passed=(not has_critical_failure and score >= 3),
        has_critical_failure=has_critical_failure,
        execution_status=execution_status,
        checks=checks or [],
        judge_verdict=judge_verdict,
    )


# ============================================================================
# 1. Deliberate Violation Demonstrations
# ============================================================================


def test_demonstration_planted_token_leakage_triggers_critical_regression(
    base_metadata: RunMetadata,
    valid_lead_result: LeadQualificationResult,
    valid_handoff_result: OutreachHandoff,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Deliberate planted token leakage fails deterministic check and flags critical regression."""
    # Step 1: Execute deterministic checks on an outreach draft containing a planted token
    sample_case = load_dataset()[0].model_copy(deep=True)
    sample_case.expected.forbidden_terms = ["PLANTED_SECRET_TOKEN_LEAKAGE"]

    payload = dict(valid_email_draft_payload)
    payload["body"] = "Hello, your token is PLANTED_SECRET_TOKEN_LEAKAGE. Welcome."
    leaked_draft = OutreachDraftResult.model_validate(payload)

    coord_result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=leaked_draft,
    )

    check_res = check_forbidden_leakage(coord_result, sample_case)
    assert check_res is not None
    assert check_res.passed is False
    assert check_res.severity == CheckSeverity.CRITICAL_BLOCKING
    assert "PLANTED_SECRET_TOKEN_LEAKAGE" in check_res.message

    # Step 2: Form current baseline record with critical check failure
    b_case = _build_valid_case_result("CASE-001", score=4, has_critical_failure=False)
    c_case = _build_valid_case_result(
        "CASE-001",
        score=4,
        has_critical_failure=True,
        checks=[check_res],
    )

    base = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    # Step 3: Run comparison and verify critical deterministic classification
    diff = compare_against_baseline(current=curr, baseline=base)
    assert diff.has_regressions is True
    assert diff.critical_deterministic_regressions == ["CASE-001"]
    assert diff.semantic_regressions == []


def test_demonstration_word_count_ceiling_breach(
    base_metadata: RunMetadata,
    valid_lead_result: LeadQualificationResult,
    valid_handoff_result: OutreachHandoff,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Deliberate word count breach fails deterministic check and flags critical regression."""
    sample_case = load_dataset()[0].model_copy(deep=True)
    sample_case.expected.max_word_count = 150

    payload = dict(valid_email_draft_payload)
    payload["body"] = "word " * 250  # 250 words exceeds 150 max_word_count
    overlength_draft = OutreachDraftResult.model_validate(payload)

    coord_result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=overlength_draft,
    )

    check_res = check_word_count_ceiling(coord_result, sample_case)
    assert check_res is not None
    assert check_res.passed is False
    assert check_res.severity == CheckSeverity.CRITICAL_BLOCKING
    assert "exceeded ceiling" in check_res.message

    b_case = _build_valid_case_result("CASE-001", score=4, has_critical_failure=False)
    c_case = _build_valid_case_result(
        "CASE-001",
        score=4,
        has_critical_failure=True,
        checks=[check_res],
    )

    base = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    diff = compare_against_baseline(current=curr, baseline=base)
    assert diff.has_regressions is True
    assert diff.critical_deterministic_regressions == ["CASE-001"]
    assert diff.semantic_regressions == []


def test_demonstration_semantic_score_drop_triggers_semantic_regression(
    base_metadata: RunMetadata,
) -> None:
    """Deliberate semantic score degradation is strictly classified in semantic_regressions."""
    b_case = _build_valid_case_result("CASE-001", score=4)
    # Score drops to 2 (failing threshold)
    c_case = _build_valid_case_result("CASE-001", score=2)

    base = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    diff = compare_against_baseline(current=curr, baseline=base)
    assert diff.has_regressions is True
    assert diff.semantic_regressions == ["CASE-001"]
    # Crucial safeguard: MUST NOT be placed in critical_deterministic_regressions
    assert diff.critical_deterministic_regressions == []


def test_demonstration_channel_mismatch_failure(
    base_metadata: RunMetadata,
    valid_lead_result: LeadQualificationResult,
    valid_email_draft_result: OutreachDraftResult,
) -> None:
    """Generating email draft for a LinkedIn-configured channel fails critical check."""
    from agent_eval_harness.evaluation.checks import check_channel_rules

    cases = load_dataset()
    linkedin_case = next(c for c in cases if c.outreach_config.channel == OutreachChannel.LINKEDIN)

    handoff = OutreachHandoff(
        lead=valid_lead_result,
        channel=OutreachChannel.EMAIL,  # Wrong channel
        target_persona="CISO",
    )
    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=handoff,
        draft_result=valid_email_draft_result,
    )

    res = check_channel_rules(result, linkedin_case)
    assert res is not None
    assert res.passed is False
    assert res.severity == CheckSeverity.CRITICAL_BLOCKING
    assert "channel mismatch" in res.message


# ============================================================================
# 2. CLI Deterministic Exit Code Tests
# ============================================================================


def test_cli_exit_code_0_clean_comparison(tmp_path: Path, base_metadata: RunMetadata) -> None:
    """CLI exits with 0 when current and baseline are identical and clean."""
    case1 = _build_valid_case_result("CASE-001", score=4)
    record = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "current.json"
    out_path = tmp_path / "summary.md"

    b_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    c_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    exit_code = cli_main(
        ["--baseline", str(b_path), "--current", str(c_path), "--output", str(out_path)]
    )
    assert exit_code == 0
    assert out_path.exists()
    assert "Regressions Detected:** NO (PASS)" in out_path.read_text(encoding="utf-8")


def test_cli_exit_code_1_regressions_detected(tmp_path: Path, base_metadata: RunMetadata) -> None:
    """CLI exits with 1 when regressions are detected."""
    b_case = _build_valid_case_result("CASE-001", score=4)
    c_case = _build_valid_case_result("CASE-001", score=2)  # Regressed

    base_rec = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr_rec = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "current.json"
    b_path.write_text(base_rec.model_dump_json(indent=2), encoding="utf-8")
    c_path.write_text(curr_rec.model_dump_json(indent=2), encoding="utf-8")

    exit_code = cli_main(["--baseline", str(b_path), "--current", str(c_path)])
    assert exit_code == 1


def test_cli_exit_code_2_incompatible_baseline(tmp_path: Path, base_metadata: RunMetadata) -> None:
    """CLI exits with 2 when current and baseline are incompatible."""
    case1 = _build_valid_case_result("CASE-001", score=4)
    base_rec = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    # Incompatible rubric version
    bad_meta = base_metadata.model_copy(update={"rubric_version": "9.9.9"})
    curr_rec = BaselineRecord(
        metadata=bad_meta,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "current.json"
    b_path.write_text(base_rec.model_dump_json(indent=2), encoding="utf-8")
    c_path.write_text(curr_rec.model_dump_json(indent=2), encoding="utf-8")

    exit_code = cli_main(["--baseline", str(b_path), "--current", str(c_path)])
    assert exit_code == 2


def test_cli_exit_code_3_missing_baseline(tmp_path: Path, base_metadata: RunMetadata) -> None:
    """CLI exits with 3 when baseline file does not exist on disk."""
    case1 = _build_valid_case_result("CASE-001", score=4)
    curr_rec = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    b_path = tmp_path / "non_existent_baseline.json"
    c_path = tmp_path / "current.json"
    c_path.write_text(curr_rec.model_dump_json(indent=2), encoding="utf-8")

    exit_code = cli_main(["--baseline", str(b_path), "--current", str(c_path)])
    assert exit_code == 3


def test_cli_exit_code_4_corrupt_json(tmp_path: Path, base_metadata: RunMetadata) -> None:
    """CLI exits with 4 when record file is malformed JSON or invalid schema."""
    case1 = _build_valid_case_result("CASE-001", score=4)
    curr_rec = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    # 1. Corrupt baseline
    b_path = tmp_path / "corrupt_baseline.json"
    b_path.write_text("NOT_VALID_JSON{", encoding="utf-8")

    c_path = tmp_path / "current.json"
    c_path.write_text(curr_rec.model_dump_json(indent=2), encoding="utf-8")

    exit_code = cli_main(["--baseline", str(b_path), "--current", str(c_path)])
    assert exit_code == 4

    # 2. Corrupt current
    good_b = tmp_path / "good_baseline.json"
    good_b.write_text(curr_rec.model_dump_json(indent=2), encoding="utf-8")
    corrupt_c = tmp_path / "corrupt_current.json"
    corrupt_c.write_text("NOT_VALID_JSON{", encoding="utf-8")

    exit_code2 = cli_main(["--baseline", str(good_b), "--current", str(corrupt_c)])
    assert exit_code2 == 4


def test_cli_output_write_oserror(
    tmp_path: Path, base_metadata: RunMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI handles OSError during file write gracefully by printing warning."""
    case1 = _build_valid_case_result("CASE-001", score=4)
    record = BaselineRecord(
        metadata=base_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "current.json"
    b_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    c_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def mock_write_text(*args: Any, **kwargs: Any) -> None:
        raise OSError("Read-only filesystem")

    monkeypatch.setattr(Path, "write_text", mock_write_text)

    # Execution should not raise exception, but return 0 with warning
    exit_code = cli_main(
        [
            "--baseline",
            str(b_path),
            "--current",
            str(c_path),
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert exit_code == 0


def test_cli_module_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies compare_cli can be invoked via runpy as __main__."""
    import runpy
    import sys

    monkeypatch.delitem(sys.modules, "agent_eval_harness.evaluation.compare_cli", raising=False)
    with patch("sys.argv", ["compare_cli", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("agent_eval_harness.evaluation.compare_cli", run_name="__main__")
        assert exc_info.value.code == 0


def test_cli_missing_current_file(tmp_path: Path) -> None:
    """CLI exits with 4 when current evaluation file is missing."""
    b_path = tmp_path / "baseline.json"
    b_path.write_text("{}", encoding="utf-8")
    missing_c = tmp_path / "missing_current.json"

    exit_code = cli_main(["--baseline", str(b_path), "--current", str(missing_c)])
    assert exit_code == 4


def test_cli_entrypoint_with_sys_argv() -> None:
    """CLI main executes cleanly with mocked sys.argv."""
    with patch("sys.argv", ["compare_cli", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code == 0
