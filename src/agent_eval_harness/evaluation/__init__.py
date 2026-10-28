"""Evaluation package for deterministic agent testing, datasets, and guardrail checks."""

from agent_eval_harness.evaluation.baseline import (
    BaselineComparisonResult,
    BaselineComparisonStatus,
    BaselineRecord,
    RunMetadata,
    compare_against_baseline,
    compute_dataset_hash,
)
from agent_eval_harness.evaluation.checks import (
    ALL_CHECKS,
    check_channel_rules,
    check_forbidden_leakage,
    check_lifecycle_status,
    check_qualification_status,
    check_required_terms,
    check_score_bounds,
    check_word_count_ceiling,
)
from agent_eval_harness.evaluation.dataset import (
    DEFAULT_DATASET_PATH,
    dump_dataset,
    load_dataset,
)
from agent_eval_harness.evaluation.judge import LLMJudge
from agent_eval_harness.evaluation.models import (
    CaseEvaluationResult,
    CheckResult,
    CheckSeverity,
    DatasetEvaluationSummary,
    DimensionScore,
    EvaluationCase,
    ExpectedAssertions,
    JudgeStatus,
    JudgeVerdict,
    RawJudgeResponse,
)
from agent_eval_harness.evaluation.rubric import (
    DEFAULT_RUBRIC,
    DimensionCriteria,
    EvaluationRubric,
    RubricDimension,
)
from agent_eval_harness.evaluation.runner import DeterministicEvaluationRunner

__all__ = [
    "ALL_CHECKS",
    "BaselineComparisonResult",
    "BaselineComparisonStatus",
    "BaselineRecord",
    "CaseEvaluationResult",
    "CheckResult",
    "CheckSeverity",
    "DEFAULT_DATASET_PATH",
    "DEFAULT_RUBRIC",
    "DatasetEvaluationSummary",
    "DeterministicEvaluationRunner",
    "DimensionCriteria",
    "DimensionScore",
    "EvaluationCase",
    "EvaluationRubric",
    "ExpectedAssertions",
    "JudgeStatus",
    "JudgeVerdict",
    "LLMJudge",
    "RawJudgeResponse",
    "RubricDimension",
    "RunMetadata",
    "check_channel_rules",
    "check_forbidden_leakage",
    "check_lifecycle_status",
    "check_qualification_status",
    "check_required_terms",
    "check_score_bounds",
    "check_word_count_ceiling",
    "compare_against_baseline",
    "compute_dataset_hash",
    "dump_dataset",
    "load_dataset",
]
