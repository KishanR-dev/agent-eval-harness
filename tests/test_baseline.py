"""Comprehensive tests for baseline models, hashing, comparison policy, and regression detection."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_eval_harness.coordinator import CoordinatorStatus
from agent_eval_harness.evaluation.baseline import (
    BaselineComparisonStatus,
    BaselineRecord,
    RunMetadata,
    compare_against_baseline,
    compute_dataset_hash,
)
from agent_eval_harness.evaluation.dataset import DEFAULT_DATASET_PATH, load_dataset
from agent_eval_harness.evaluation.models import (
    CaseEvaluationResult,
    DimensionScore,
    JudgeStatus,
    JudgeVerdict,
)
from agent_eval_harness.evaluation.rubric import RubricDimension
from agent_eval_harness.exceptions import BaselineIncompatibleError, BaselineUnavailableError


@pytest.fixture
def sample_dataset_hash() -> str:
    """Canonical hash of the synthetic dataset."""
    return compute_dataset_hash(DEFAULT_DATASET_PATH)


@pytest.fixture
def mock_run_metadata(sample_dataset_hash: str) -> RunMetadata:
    """Fixture providing valid reproducibility metadata for replay mode."""
    return RunMetadata(
        schema_version="1.0.0",
        timestamp=datetime.now(UTC),
        commit_sha=None,  # Uncommitted run
        dataset_version="1.0.0",
        dataset_hash=sample_dataset_hash,
        rubric_version="1.0.0",
        execution_mode="replay",
        model_id=None,
    )


def _make_case_result(
    case_id: str,
    passed: bool = True,
    has_critical_failure: bool = False,
    execution_status: CoordinatorStatus = CoordinatorStatus.COMPLETED,
    overall_score: float = 4.0,
    judge_status: JudgeStatus = JudgeStatus.COMPLETED_PASS,
) -> CaseEvaluationResult:
    """Helper constructing valid CaseEvaluationResult models."""
    scores = [
        DimensionScore(
            dimension=dim,
            score=int(overall_score),
            rationale="Test rationale.",
        )
        for dim in RubricDimension
    ]
    judge_verdict = JudgeVerdict(
        rubric_version="1.0.0",
        model_identifier="test-evaluator",
        status=judge_status,
        scores=scores,
    )
    return CaseEvaluationResult(
        case_id=case_id,
        passed=passed,
        has_critical_failure=has_critical_failure,
        execution_status=execution_status,
        checks=[],
        judge_verdict=judge_verdict,
    )


# ============================================================================
# 1. Canonical Dataset Hashing Tests
# ============================================================================


def test_compute_dataset_hash_from_path() -> None:
    """Dataset hashing from file path returns sha256 formatted digest."""
    digest = compute_dataset_hash(DEFAULT_DATASET_PATH)
    assert digest.startswith("sha256:")
    assert len(digest) == 7 + 64


def test_compute_dataset_hash_from_sequence() -> None:
    """Dataset hashing from loaded EvaluationCase sequence produces identical hash."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    hash_from_cases = compute_dataset_hash(cases)
    hash_from_path = compute_dataset_hash(DEFAULT_DATASET_PATH)
    assert hash_from_cases == hash_from_path


def test_compute_dataset_hash_formatting_invariance(tmp_path: Path) -> None:
    """Equivalent dataset cases with different whitespace/ordering produce identical hash."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    # Reverse case order and dump with custom formatting
    reversed_cases = list(reversed(cases))
    dump_data = [c.model_dump(mode="json") for c in reversed_cases]

    temp_dataset = tmp_path / "custom_formatted.json"
    temp_dataset.write_text(json.dumps(dump_data, indent=4), encoding="utf-8")

    hash1 = compute_dataset_hash(DEFAULT_DATASET_PATH)
    hash2 = compute_dataset_hash(temp_dataset)
    assert hash1 == hash2


def test_compute_dataset_hash_rejects_non_list_file(tmp_path: Path) -> None:
    """compute_dataset_hash raises ValueError if JSON root is not a list."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset root must be a list"):
        compute_dataset_hash(bad_file)


# ============================================================================
# 2. RunMetadata & BaselineRecord Invariant Tests
# ============================================================================


def test_run_metadata_uncommitted_run(sample_dataset_hash: str) -> None:
    """Uncommitted run stores commit_sha as None without error."""
    meta = RunMetadata(
        timestamp=datetime.now(UTC),
        commit_sha=None,
        dataset_version="1.0.0",
        dataset_hash=sample_dataset_hash,
        rubric_version="1.0.0",
        execution_mode="replay",
        model_id=None,
    )
    assert meta.commit_sha is None
    assert meta.execution_mode == "replay"


def test_run_metadata_replay_mode_rejects_live_model_id(sample_dataset_hash: str) -> None:
    """Replay execution mode rejects real provider model identifiers."""
    with pytest.raises(ValidationError, match="must have model_id as None or 'offline-replay'"):
        RunMetadata(
            timestamp=datetime.now(UTC),
            dataset_version="1.0.0",
            dataset_hash=sample_dataset_hash,
            rubric_version="1.0.0",
            execution_mode="replay",
            model_id="gpt-4o-2024-08-06",
        )


def test_run_metadata_live_mode_validation(sample_dataset_hash: str) -> None:
    """Live execution mode requires non-empty model_id."""
    # Valid live metadata
    meta = RunMetadata(
        timestamp=datetime.now(UTC),
        commit_sha="a" * 40,
        dataset_version="1.0.0",
        dataset_hash=sample_dataset_hash,
        rubric_version="1.0.0",
        execution_mode="live",
        model_id="gemini-2.5-flash",
    )
    assert meta.model_id == "gemini-2.5-flash"

    # Invalid live metadata (missing model_id)
    with pytest.raises(ValidationError, match="Live execution mode requires a non-empty model_id"):
        RunMetadata(
            timestamp=datetime.now(UTC),
            dataset_version="1.0.0",
            dataset_hash=sample_dataset_hash,
            rubric_version="1.0.0",
            execution_mode="live",
            model_id=None,
        )


def test_baseline_record_invariants_count_mismatch(mock_run_metadata: RunMetadata) -> None:
    """BaselineRecord rejects total_cases not matching case_results length."""
    case1 = _make_case_result("CASE-001", passed=True)
    with pytest.raises(ValidationError, match="total_cases .* does not match"):
        BaselineRecord(
            metadata=mock_run_metadata,
            total_cases=2,  # Claims 2, only provides 1
            pass_count=1,
            fail_count=1,
            pass_rate=0.5,
            case_results={"CASE-001": case1},
        )


def test_baseline_record_invariants_pass_fail_sum(mock_run_metadata: RunMetadata) -> None:
    """BaselineRecord rejects pass_count + fail_count != total_cases."""
    case1 = _make_case_result("CASE-001", passed=True)
    with pytest.raises(ValidationError, match="must equal total_cases"):
        BaselineRecord(
            metadata=mock_run_metadata,
            total_cases=1,
            pass_count=1,
            fail_count=1,  # Sum = 2 != 1
            pass_rate=1.0,
            case_results={"CASE-001": case1},
        )


def test_baseline_record_invariants_actual_pass_count(mock_run_metadata: RunMetadata) -> None:
    """BaselineRecord rejects pass_count not matching actual passed outcomes."""
    case1 = _make_case_result("CASE-001", passed=True)
    with pytest.raises(ValidationError, match="does not match actual count"):
        BaselineRecord(
            metadata=mock_run_metadata,
            total_cases=1,
            pass_count=0,  # Claims 0 passed, but case1.passed is True
            fail_count=1,
            pass_rate=0.0,
            case_results={"CASE-001": case1},
        )


def test_baseline_record_invariants_pass_rate_calculation(mock_run_metadata: RunMetadata) -> None:
    """BaselineRecord rejects inconsistent pass_rate."""
    case1 = _make_case_result("CASE-001", passed=True)
    with pytest.raises(ValidationError, match="does not match calculated rate"):
        BaselineRecord(
            metadata=mock_run_metadata,
            total_cases=1,
            pass_count=1,
            fail_count=0,
            pass_rate=0.5,  # Calculated is 1.0
            case_results={"CASE-001": case1},
        )


def test_baseline_record_invariants_key_mismatch(mock_run_metadata: RunMetadata) -> None:
    """BaselineRecord rejects case_results dict key differing from case_id."""
    case1 = _make_case_result("CASE-001", passed=True)
    with pytest.raises(ValidationError, match="does not match CaseEvaluationResult.case_id"):
        BaselineRecord(
            metadata=mock_run_metadata,
            total_cases=1,
            pass_count=1,
            fail_count=0,
            pass_rate=1.0,
            case_results={"WRONG-KEY": case1},
        )


# ============================================================================
# 3. Compatibility & Comparison Logic Tests
# ============================================================================


def test_compare_against_baseline_unavailable_normal(mock_run_metadata: RunMetadata) -> None:
    """Missing baseline in normal mode returns BASELINE_UNAVAILABLE without crashing."""
    case1 = _make_case_result("CASE-001", passed=True)
    current = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )
    result = compare_against_baseline(current=current, baseline=None, strict=False)
    assert result.status == BaselineComparisonStatus.BASELINE_UNAVAILABLE
    assert result.is_compatible is False
    assert result.has_regressions is False
    assert "unavailable" in result.summary.lower()


def test_compare_against_baseline_unavailable_strict(mock_run_metadata: RunMetadata) -> None:
    """Missing baseline in strict mode raises BaselineUnavailableError."""
    case1 = _make_case_result("CASE-001", passed=True)
    current = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )
    with pytest.raises(BaselineUnavailableError, match="No reference baseline record was provided"):
        compare_against_baseline(current=current, baseline=None, strict=True)


def test_compare_against_baseline_incompatible_dimensions(mock_run_metadata: RunMetadata) -> None:
    """Different dataset hash, schema, rubric, or execution mode triggers INCOMPATIBLE."""
    case1 = _make_case_result("CASE-001", passed=True)
    current = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": case1},
    )

    # 1. Dataset hash mismatch
    bad_meta = mock_run_metadata.model_copy(update={"dataset_hash": "sha256:different"})
    base_bad = current.model_copy(update={"metadata": bad_meta})
    res = compare_against_baseline(current=current, baseline=base_bad, strict=False)
    assert res.status == BaselineComparisonStatus.INCOMPATIBLE
    assert any("Dataset hash mismatch" in r for r in res.incompatibility_reasons)

    # In strict mode raises
    with pytest.raises(BaselineIncompatibleError, match="Dataset hash mismatch"):
        compare_against_baseline(current=current, baseline=base_bad, strict=True)

    # 2. Execution mode mismatch
    live_meta = mock_run_metadata.model_copy(
        update={"execution_mode": "live", "model_id": "test-model"}
    )
    base_live = current.model_copy(update={"metadata": live_meta})
    res_mode = compare_against_baseline(current=current, baseline=base_live, strict=False)
    assert res_mode.status == BaselineComparisonStatus.INCOMPATIBLE
    assert any("Execution mode mismatch" in r for r in res_mode.incompatibility_reasons)

    # 3. Schema version mismatch
    bad_schema_meta = mock_run_metadata.model_copy(update={"schema_version": "0.9.0"})
    base_schema = current.model_copy(update={"metadata": bad_schema_meta})
    res_schema = compare_against_baseline(current=current, baseline=base_schema, strict=False)
    assert res_schema.status == BaselineComparisonStatus.INCOMPATIBLE
    assert any("Schema version mismatch" in r for r in res_schema.incompatibility_reasons)


# ============================================================================
# 4. Regression Taxonomy Tests (Critical Deterministic vs Semantic)
# ============================================================================


def test_compare_critical_deterministic_regression(mock_run_metadata: RunMetadata) -> None:
    """Critical guardrail failure is flagged in critical_deterministic_regressions."""
    b_case = _make_case_result("CASE-001", passed=True, has_critical_failure=False)
    c_case = _make_case_result("CASE-001", passed=False, has_critical_failure=True)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.status == BaselineComparisonStatus.COMPARABLE
    assert res.has_regressions is True
    assert res.critical_deterministic_regressions == ["CASE-001"]
    assert res.semantic_regressions == []  # MUST NOT be classified as semantic
    assert res.regressed_cases == ["CASE-001"]


def test_compare_coordinator_failure_is_critical_regression(
    mock_run_metadata: RunMetadata,
) -> None:
    """Coordinator execution status regressing to FAILED is a critical deterministic regression."""
    b_case = _make_case_result(
        "CASE-001", passed=True, execution_status=CoordinatorStatus.COMPLETED
    )
    c_case = _make_case_result("CASE-001", passed=False, execution_status=CoordinatorStatus.FAILED)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.has_regressions is True
    assert res.critical_deterministic_regressions == ["CASE-001"]
    assert res.semantic_regressions == []


def test_compare_semantic_regression_score_drop(mock_run_metadata: RunMetadata) -> None:
    """Semantic score drop below passing threshold (3.0) flags semantic_regressions only."""
    b_case = _make_case_result(
        "CASE-001",
        passed=True,
        has_critical_failure=False,
        overall_score=4.0,
        judge_status=JudgeStatus.COMPLETED_PASS,
    )
    c_case = _make_case_result(
        "CASE-001",
        passed=False,
        has_critical_failure=False,
        overall_score=2.0,
        judge_status=JudgeStatus.COMPLETED_FAIL,
    )

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.has_regressions is True
    assert res.semantic_regressions == ["CASE-001"]
    # Crucial safeguard: MUST NOT be placed in critical_deterministic_regressions
    assert res.critical_deterministic_regressions == []
    assert res.score_deltas["CASE-001"]["relevance_positioning"] == -2.0


def test_compare_existing_critical_failure_in_both_runs(mock_run_metadata: RunMetadata) -> None:
    """Critical guardrail failure already present in baseline is not flagged as a regression."""
    b_case = _make_case_result("CASE-001", passed=False, has_critical_failure=True)
    c_case = _make_case_result("CASE-001", passed=False, has_critical_failure=True)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.status == BaselineComparisonStatus.COMPARABLE
    assert res.has_regressions is False
    assert res.critical_deterministic_regressions == []
    assert res.semantic_regressions == []
    assert res.regressed_cases == []
    assert res.unchanged_cases == ["CASE-001"]


def test_compare_existing_coordinator_failure_in_both_runs(mock_run_metadata: RunMetadata) -> None:
    """Coordinator failure already present in baseline is treated as unchanged, not a regression."""
    b_case = _make_case_result("CASE-001", passed=False, execution_status=CoordinatorStatus.FAILED)
    c_case = _make_case_result("CASE-001", passed=False, execution_status=CoordinatorStatus.FAILED)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.status == BaselineComparisonStatus.COMPARABLE
    assert res.has_regressions is False
    assert res.critical_deterministic_regressions == []
    assert res.semantic_regressions == []
    assert res.regressed_cases == []
    assert res.unchanged_cases == ["CASE-001"]


def test_compare_missing_and_added_cases(mock_run_metadata: RunMetadata) -> None:
    """Missing cases in current run are logged; strict mode treats missing cases as regressions."""
    c1 = _make_case_result("CASE-001", passed=True)
    c2 = _make_case_result("CASE-002", passed=True)
    c3 = _make_case_result("CASE-003", passed=True)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=2,
        pass_count=2,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c1, "CASE-002": c2},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=2,
        pass_count=2,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c1, "CASE-003": c3},
    )

    # In normal mode: missing cases logged, has_regressions=False
    res_normal = compare_against_baseline(current=curr, baseline=base, strict=False)
    assert res_normal.missing_in_current == ["CASE-002"]
    assert res_normal.missing_in_baseline == ["CASE-003"]
    assert res_normal.has_regressions is False

    # In strict mode: missing cases trigger has_regressions=True
    res_strict = compare_against_baseline(current=curr, baseline=base, strict=True)
    assert res_strict.missing_in_current == ["CASE-002"]
    assert res_strict.has_regressions is True


def test_compare_improved_cases(mock_run_metadata: RunMetadata) -> None:
    """Previously failing cases that now pass are tracked in improved_cases."""
    c1_fail = _make_case_result("CASE-001", passed=False)
    c1_pass = _make_case_result("CASE-001", passed=True)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c1_fail},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c1_pass},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.has_regressions is False
    assert res.improved_cases == ["CASE-001"]
    assert res.regressed_cases == []


def test_compare_against_baseline_workflows_without_judge(mock_run_metadata: RunMetadata) -> None:
    """Correctly skipped workflows without judge verdict are compared on deterministic outcomes."""
    c1 = CaseEvaluationResult(
        case_id="CASE-001",
        passed=True,
        has_critical_failure=False,
        execution_status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
        checks=[],
        judge_verdict=None,
    )
    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c1},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c1},
    )
    res = compare_against_baseline(current=curr, baseline=base)
    assert res.status == BaselineComparisonStatus.COMPARABLE
    assert res.unchanged_cases == ["CASE-001"]
    assert res.has_regressions is False


def test_compare_against_baseline_failing_verdict_dimension_drop(
    mock_run_metadata: RunMetadata,
) -> None:
    """When both verdicts fail, a dimension dropping below 3 still flags regression."""
    dims = list(RubricDimension)
    # Baseline: dimension 0 is 3, dimension 1 is 3, dimension 2 is 2 -> overall COMPLETED_FAIL
    b_scores = [
        DimensionScore(dimension=dims[0], score=3, rationale="Adequate score provided."),
        DimensionScore(dimension=dims[1], score=3, rationale="Adequate score provided."),
        DimensionScore(dimension=dims[2], score=2, rationale="Subpar score provided."),
    ]
    b_verdict = JudgeVerdict(
        rubric_version="1.0.0",
        model_identifier="test-evaluator",
        status=JudgeStatus.COMPLETED_FAIL,
        scores=b_scores,
    )
    b_case = CaseEvaluationResult(
        case_id="CASE-001",
        passed=False,
        has_critical_failure=False,
        execution_status=CoordinatorStatus.COMPLETED,
        checks=[],
        judge_verdict=b_verdict,
    )

    # Current: dimension 0 dropped to 2, dimension 1 is 3, dimension 2 is 2 -> COMPLETED_FAIL
    c_scores = [
        DimensionScore(dimension=dims[0], score=2, rationale="Regressed score detected."),
        DimensionScore(dimension=dims[1], score=3, rationale="Adequate score provided."),
        DimensionScore(dimension=dims[2], score=2, rationale="Subpar score provided."),
    ]
    c_verdict = JudgeVerdict(
        rubric_version="1.0.0",
        model_identifier="test-evaluator",
        status=JudgeStatus.COMPLETED_FAIL,
        scores=c_scores,
    )
    c_case = CaseEvaluationResult(
        case_id="CASE-001",
        passed=False,
        has_critical_failure=False,
        execution_status=CoordinatorStatus.COMPLETED,
        checks=[],
        judge_verdict=c_verdict,
    )

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.has_regressions is True
    assert res.semantic_regressions == ["CASE-001"]
    assert res.critical_deterministic_regressions == []
    assert res.score_deltas["CASE-001"][dims[0].value] == -1.0


def test_compare_against_baseline_inconclusive_to_pass(mock_run_metadata: RunMetadata) -> None:
    """Inconclusive baseline to pass exercises missing dimension and empty delta paths."""
    b_verdict = JudgeVerdict(
        rubric_version="1.0.0",
        model_identifier="test-evaluator",
        status=JudgeStatus.INCONCLUSIVE_OUTPUT,
        error_category="MalformedOutput",
        error_message="Judge output was invalid JSON",
        scores=[],
    )
    b_case = CaseEvaluationResult(
        case_id="CASE-001",
        passed=False,
        has_critical_failure=False,
        execution_status=CoordinatorStatus.COMPLETED,
        checks=[],
        judge_verdict=b_verdict,
    )

    c_case = _make_case_result("CASE-001", passed=True, overall_score=4.0)

    base = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=0,
        fail_count=1,
        pass_rate=0.0,
        case_results={"CASE-001": b_case},
    )
    curr = BaselineRecord(
        metadata=mock_run_metadata,
        total_cases=1,
        pass_count=1,
        fail_count=0,
        pass_rate=1.0,
        case_results={"CASE-001": c_case},
    )

    res = compare_against_baseline(current=curr, baseline=base)
    assert res.improved_cases == ["CASE-001"]
    assert "CASE-001" not in res.score_deltas  # No matching dimensions in baseline
    assert res.has_regressions is False
