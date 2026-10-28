"""Evaluation runner executing deterministic checks and optional rubric judge against workflows."""

from collections.abc import Sequence

from agent_eval_harness.coordinator import CoordinatorResult, CoordinatorStatus, WorkflowCoordinator
from agent_eval_harness.evaluation.checks import ALL_CHECKS
from agent_eval_harness.evaluation.judge import LLMJudge
from agent_eval_harness.evaluation.models import (
    CaseEvaluationResult,
    CheckResult,
    CheckSeverity,
    DatasetEvaluationSummary,
    EvaluationCase,
    JudgeStatus,
    JudgeVerdict,
)


class DeterministicEvaluationRunner:
    """Evaluates workflow results against deterministic assertions and optional judge."""

    def __init__(self, judge: LLMJudge | None = None) -> None:
        """Initialize evaluation runner.

        Args:
            judge: Optional LLMJudge instance for qualitative semantic evaluation.
        """
        self.judge = judge

    def evaluate_result(
        self,
        case: EvaluationCase,
        result: CoordinatorResult,
        judge: LLMJudge | None = None,
    ) -> CaseEvaluationResult:
        """Run all applicable deterministic checks and optional judge on a single workflow result.

        Args:
            case: The evaluation case specifying expected properties.
            result: The coordinator result produced by the workflow.
            judge: Optional override for the runner's configured LLMJudge.

        Returns:
            CaseEvaluationResult detailing pass/fail status, check diagnostics, and judge verdict.
        """
        check_results: list[CheckResult] = []
        has_critical_failure = False

        for check_fn in ALL_CHECKS:
            check_res = check_fn(result, case)
            if check_res is not None:
                check_results.append(check_res)
                if not check_res.passed and check_res.severity == CheckSeverity.CRITICAL_BLOCKING:
                    has_critical_failure = True

        deterministic_passed = all(cr.passed for cr in check_results)

        # Optional semantic judge tier
        effective_judge = judge if judge is not None else self.judge
        judge_verdict: JudgeVerdict | None = None

        if effective_judge is not None:
            judge_verdict = effective_judge.evaluate(
                lead_input=case.lead_input,
                outreach_config=case.outreach_config,
                result=result,
            )

        # Case pass/fail determination:
        # Coordinator failure, critical failure, or deterministic failure unconditionally fails case
        if (
            result.status == CoordinatorStatus.FAILED
            or has_critical_failure
            or not deterministic_passed
        ):
            case_passed = False
        elif (
            judge_verdict is not None and judge_verdict.status != JudgeStatus.SKIPPED_NON_APPLICABLE
        ):
            case_passed = judge_verdict.passed is True
        else:
            # Either no judge was run, or judge was SKIPPED_NON_APPLICABLE on a valid skip
            case_passed = True

        return CaseEvaluationResult(
            case_id=case.case_id,
            passed=case_passed,
            has_critical_failure=has_critical_failure,
            execution_status=result.status,
            checks=check_results,
            judge_verdict=judge_verdict,
        )

    def evaluate_dataset(
        self,
        cases: Sequence[EvaluationCase],
        coordinator: WorkflowCoordinator,
        judge: LLMJudge | None = None,
    ) -> DatasetEvaluationSummary:
        """Execute the workflow coordinator across a dataset and aggregate evaluations.

        Args:
            cases: List of evaluation test cases.
            coordinator: Configured WorkflowCoordinator instance.
            judge: Optional LLMJudge instance for semantic grading.

        Returns:
            DatasetEvaluationSummary with pass rates and detailed per-case results.
        """
        case_results: list[CaseEvaluationResult] = []
        passed_count = 0
        critical_count = 0

        for case in cases:
            coordinator_res = coordinator.run(
                lead_input=case.lead_input,
                outreach_config=case.outreach_config,
            )
            eval_res = self.evaluate_result(case, coordinator_res, judge=judge)
            case_results.append(eval_res)

            if eval_res.passed:
                passed_count += 1
            if eval_res.has_critical_failure:
                critical_count += 1

        total = len(cases)
        failed_count = total - passed_count
        pass_rate = (passed_count / total) if total > 0 else 0.0

        return DatasetEvaluationSummary(
            dataset_version=cases[0].dataset_version if cases else "1.0.0",
            total_cases=total,
            passed_cases=passed_count,
            failed_cases=failed_count,
            critical_failures=critical_count,
            pass_rate=pass_rate,
            case_results=case_results,
        )
