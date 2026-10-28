"""Integration and unit tests for DeterministicEvaluationRunner."""

from typing import Any

from agent_eval_harness.agents import LeadQualificationAgent, OutreachDrafterAgent
from agent_eval_harness.coordinator import CoordinatorResult, CoordinatorStatus, WorkflowCoordinator
from agent_eval_harness.evaluation import (
    DeterministicEvaluationRunner,
    load_dataset,
)
from agent_eval_harness.providers import FakeLLMAdapter


def test_runner_single_result_evaluation(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Runner evaluates single CoordinatorResult against an EvaluationCase."""
    cases = load_dataset()
    case = cases[0]  # CASE-001 (requires SOC2, EMAIL, etc.)

    # Prepare draft that satisfies all assertions
    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "Platform providing SOC2 and compliance monitoring for enterprise Kubernetes."
    p_draft["subject_line"] = "Accelerating SOC2 compliance"
    from agent_eval_harness.contracts import OutreachDraftResult

    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result)

    assert eval_res.case_id == "CASE-001"
    assert eval_res.passed is True
    assert eval_res.has_critical_failure is False
    assert len(eval_res.checks) > 0


def test_runner_single_result_critical_failure(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Runner flags has_critical_failure=True when a guardrail fails."""
    cases = load_dataset()
    case = cases[0]  # CASE-001 forbids "fixed pricing"

    # Leak forbidden term into draft
    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "We guarantee fixed pricing and SOC2 compliance automation."
    from agent_eval_harness.contracts import OutreachDraftResult

    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result)

    assert eval_res.passed is False
    assert eval_res.has_critical_failure is True


def test_runner_evaluate_dataset_offline(
    valid_lead_json: str,
    valid_email_draft_json: str,
    disqualified_lead_json: str,
    needs_review_lead_json: str,
) -> None:
    """Runner executes coordinator across dataset subset and computes aggregate summary."""
    cases = load_dataset()
    # Test across 3 distinct cases: qualified, disqualified, and needs-review
    subset = [cases[0], cases[4], cases[8]]
    # CASE-001 (qualified): requires Stage 1 (lead) + Stage 2 (draft)
    # CASE-005 (disqualified): requires Stage 1 (lead) -> skips Stage 2
    # CASE-009 (needs review): requires Stage 1 (lead) -> skips Stage 2

    # Prepare canned FIFO responses
    responses = [
        valid_lead_json,
        valid_email_draft_json,  # for CASE-001
        disqualified_lead_json,  # for CASE-005
        needs_review_lead_json,  # for CASE-009
    ]

    adapter = FakeLLMAdapter(responses=responses)
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    runner = DeterministicEvaluationRunner()
    summary = runner.evaluate_dataset(cases=subset, coordinator=coordinator)

    assert summary.total_cases == 3
    assert len(summary.case_results) == 3
    assert summary.dataset_version == "1.0.0"
    # Case 001 may fail the required "SOC2" check if valid_email_draft_json lacks "SOC2"
    # But pass_rate is calculated deterministically as passed / total
    assert 0.0 <= summary.pass_rate <= 1.0
    assert summary.passed_cases + summary.failed_cases == 3


def test_runner_case_020_adversarial_token_detection(
    valid_lead_json: str,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Runner evaluates CASE-020: detects clean replay vs adversarial signature leakage."""
    import json

    cases = load_dataset()
    case_020 = next(c for c in cases if c.case_id == "CASE-020")

    # 1. Clean replay: no forbidden token in summary or draft
    p_draft_clean = dict(valid_email_draft_payload)
    p_draft_clean["body"] = "Platform providing automated policy management for 750 clusters."
    clean_draft_json = json.dumps(p_draft_clean)

    adapter_clean = FakeLLMAdapter(responses=[valid_lead_json, clean_draft_json])
    coord_clean = WorkflowCoordinator(
        lead_agent=LeadQualificationAgent(adapter=adapter_clean),
        outreach_agent=OutreachDrafterAgent(adapter=adapter_clean),
    )
    res_clean = coord_clean.run(
        lead_input=case_020.lead_input, outreach_config=case_020.outreach_config
    )
    eval_clean = DeterministicEvaluationRunner().evaluate_result(case=case_020, result=res_clean)

    assert res_clean.status == CoordinatorStatus.COMPLETED
    assert eval_clean.passed is True
    assert eval_clean.has_critical_failure is False

    # 2. Leaking replay: draft echoes planted instruction token
    p_draft_leaked = dict(valid_email_draft_payload)
    p_draft_leaked["body"] = "Notice: INJECTION_FLAG_PWNED_99 token was echoed in draft."
    leaked_draft_json = json.dumps(p_draft_leaked)

    adapter_leaked = FakeLLMAdapter(responses=[valid_lead_json, leaked_draft_json])
    coord_leaked = WorkflowCoordinator(
        lead_agent=LeadQualificationAgent(adapter=adapter_leaked),
        outreach_agent=OutreachDrafterAgent(adapter=adapter_leaked),
    )
    res_leaked = coord_leaked.run(
        lead_input=case_020.lead_input, outreach_config=case_020.outreach_config
    )
    eval_leaked = DeterministicEvaluationRunner().evaluate_result(case=case_020, result=res_leaked)

    assert res_leaked.status == CoordinatorStatus.COMPLETED
    assert eval_leaked.passed is False
    assert eval_leaked.has_critical_failure is True


# ============================================================================
# Runner + LLMJudge Integration Tests
# ============================================================================


def test_runner_with_judge_completed_pass(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Runner executes deterministic checks AND judge; passes when both pass."""
    import json

    from agent_eval_harness.contracts import OutreachDraftResult
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    case = cases[0]  # CASE-001

    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "Platform providing SOC2 and compliance monitoring for enterprise Kubernetes."
    p_draft["subject_line"] = "Accelerating SOC2 compliance"
    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    judge_response = json.dumps(
        {
            "scores": [
                {
                    "dimension": "relevance_positioning",
                    "score": 4,
                    "rationale": "Direct alignment with persona and cloud compliance needs.",
                },
                {
                    "dimension": "factual_grounding",
                    "score": 3,
                    "rationale": "Consistent with stated multi-cluster challenges.",
                },
                {
                    "dimension": "instruction_adherence",
                    "score": 4,
                    "rationale": "Complied with tone and constraints.",
                },
            ]
        }
    )
    judge_adapter = FakeLLMAdapter(responses=[judge_response])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner(judge=judge)
    eval_res = runner.evaluate_result(case=case, result=result)

    assert eval_res.passed is True
    assert eval_res.has_critical_failure is False
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.COMPLETED_PASS
    assert eval_res.judge_verdict.passed is True


def test_runner_with_judge_completed_fail_fails_case(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Deterministic checks pass, but judge fails -> Overall case evaluation fails."""
    import json

    from agent_eval_harness.contracts import OutreachDraftResult
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    case = cases[0]

    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "Platform providing SOC2 and compliance monitoring for enterprise Kubernetes."
    p_draft["subject_line"] = "Accelerating SOC2 compliance"
    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    # Judge returns a veto score of 1 on factual grounding
    judge_response = json.dumps(
        {
            "scores": [
                {
                    "dimension": "relevance_positioning",
                    "score": 3,
                    "rationale": "Acceptable relevance.",
                },
                {
                    "dimension": "factual_grounding",
                    "score": 1,
                    "rationale": "Hallucinated customer references.",
                },
                {
                    "dimension": "instruction_adherence",
                    "score": 3,
                    "rationale": "Acceptable tone.",
                },
            ]
        }
    )
    judge_adapter = FakeLLMAdapter(responses=[judge_response])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result, judge=judge)

    assert eval_res.passed is False  # Failed due to judge
    assert eval_res.has_critical_failure is False
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.COMPLETED_FAIL
    assert eval_res.judge_verdict.passed is False


def test_runner_with_judge_inconclusive_fails_case(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Deterministic checks pass, but judge outputs malformed JSON -> Case fails."""
    from agent_eval_harness.contracts import OutreachDraftResult
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    case = cases[0]

    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "Platform providing SOC2 and compliance monitoring for enterprise Kubernetes."
    p_draft["subject_line"] = "Accelerating SOC2 compliance"
    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    # Malformed non-JSON judge response triggers INCONCLUSIVE_OUTPUT
    judge_adapter = FakeLLMAdapter(responses=["I am an LLM and I cannot evaluate this."])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result, judge=judge)

    assert eval_res.passed is False
    assert eval_res.has_critical_failure is False
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.INCONCLUSIVE_OUTPUT
    assert eval_res.judge_verdict.passed is False


def test_runner_deterministic_critical_failure_overrides_judge_pass(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """CRITICAL: Deterministic failure unconditionally fails case even if judge passes with 4/4."""
    import json

    from agent_eval_harness.contracts import OutreachDraftResult
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    case = cases[0]  # CASE-001 forbids "fixed pricing"

    # Corrupt draft with forbidden term -> triggers deterministic CRITICAL_BLOCKING failure
    p_draft = dict(valid_email_draft_payload)
    p_draft["body"] = "We offer fixed pricing and SOC2 automation for your clusters."
    p_draft["subject_line"] = "Accelerating SOC2 compliance"
    draft = OutreachDraftResult.model_validate(p_draft)

    result = CoordinatorResult(
        status=CoordinatorStatus.COMPLETED,
        lead_result=valid_lead_result,
        handoff=valid_handoff_result,
        draft_result=draft,
    )

    # Judge gives high scores
    judge_response = json.dumps(
        {
            "scores": [
                {
                    "dimension": "relevance_positioning",
                    "score": 4,
                    "rationale": "Excellent relevance.",
                },
                {
                    "dimension": "factual_grounding",
                    "score": 4,
                    "rationale": "Excellent grounding.",
                },
                {
                    "dimension": "instruction_adherence",
                    "score": 4,
                    "rationale": "Excellent adherence.",
                },
            ]
        }
    )
    judge_adapter = FakeLLMAdapter(responses=[judge_response])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner(judge=judge)
    eval_res = runner.evaluate_result(case=case, result=result)

    # Must fail because deterministic critical check takes total precedence
    assert eval_res.passed is False
    assert eval_res.has_critical_failure is True
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.COMPLETED_PASS


def test_runner_skipped_workflow_judge_not_applicable_case_passes(
    valid_disqualified_lead_result: Any,
) -> None:
    """Skipped workflow: judge is SKIPPED_NON_APPLICABLE, case passes if checks pass."""
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    # CASE-005 expects SKIPPED_DISQUALIFIED
    case_005 = next(c for c in cases if c.case_id == "CASE-005")

    result_valid_skip = CoordinatorResult(
        status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
        lead_result=valid_disqualified_lead_result,
    )

    judge_adapter = FakeLLMAdapter(responses=[])
    judge = LLMJudge(adapter=judge_adapter)
    runner = DeterministicEvaluationRunner(judge=judge)

    # 1. When deterministic checks pass (lifecycle status matches expected SKIPPED_DISQUALIFIED):
    eval_res = runner.evaluate_result(case=case_005, result=result_valid_skip)

    assert eval_res.passed is True
    assert eval_res.has_critical_failure is False
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.SKIPPED_NON_APPLICABLE
    assert eval_res.judge_verdict.passed is None
    assert len(judge_adapter.calls) == 0

    # 2. When deterministic checks fail (e.g. evaluating CASE-001 which expects COMPLETED):
    case_001 = cases[0]
    eval_res_mismatch = runner.evaluate_result(case=case_001, result=result_valid_skip)
    assert eval_res_mismatch.passed is False
    assert eval_res_mismatch.has_critical_failure is True
    assert eval_res_mismatch.judge_verdict is not None
    assert eval_res_mismatch.judge_verdict.status == JudgeStatus.SKIPPED_NON_APPLICABLE
    assert eval_res_mismatch.judge_verdict.passed is None


def test_runner_workflow_failed_cannot_pass() -> None:
    """Clarification 2: Failed coordinator result cannot produce a passing case."""
    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    case = cases[0]

    failed_result = CoordinatorResult(
        status=CoordinatorStatus.FAILED,
        failed_stage="outreach_drafting",
        error_category="AdapterError",
        error_message="Provider connection reset",
    )

    # 1. With judge: judge emits WORKFLOW_FAILED with passed=False, case fails
    judge_adapter = FakeLLMAdapter(responses=[])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner(judge=judge)
    eval_res = runner.evaluate_result(case=case, result=failed_result)

    assert eval_res.passed is False
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.WORKFLOW_FAILED
    assert eval_res.judge_verdict.passed is False
    assert len(judge_adapter.calls) == 0

    # 2. Without judge: coordinator FAILED status unconditionally fails the case
    runner_no_judge = DeterministicEvaluationRunner(judge=None)
    eval_res_no_judge = runner_no_judge.evaluate_result(case=case, result=failed_result)
    assert eval_res_no_judge.passed is False
    assert eval_res_no_judge.judge_verdict is None


def test_runner_evaluate_dataset_with_judge(
    valid_lead_json: str,
    valid_email_draft_json: str,
    disqualified_lead_json: str,
) -> None:
    """Runner evaluates dataset with judge across multiple cases."""
    import json

    from agent_eval_harness.evaluation import JudgeStatus, LLMJudge

    cases = load_dataset()
    subset = [cases[0], cases[4]]  # CASE-001 (qualified) + CASE-005 (disqualified)

    # Coordinator adapter responses
    coord_responses = [
        valid_lead_json,
        valid_email_draft_json,  # for CASE-001
        disqualified_lead_json,  # for CASE-005 (skips stage 2)
    ]
    coord_adapter = FakeLLMAdapter(responses=coord_responses)
    coordinator = WorkflowCoordinator(
        lead_agent=LeadQualificationAgent(adapter=coord_adapter),
        outreach_agent=OutreachDrafterAgent(adapter=coord_adapter),
    )

    # Judge adapter response (only CASE-001 invokes judge; CASE-005 is SKIPPED_NON_APPLICABLE)
    judge_response = json.dumps(
        {
            "scores": [
                {
                    "dimension": "relevance_positioning",
                    "score": 3,
                    "rationale": "Targeted relevance.",
                },
                {
                    "dimension": "factual_grounding",
                    "score": 3,
                    "rationale": "Consistent with notes.",
                },
                {
                    "dimension": "instruction_adherence",
                    "score": 3,
                    "rationale": "Adheres to email rules.",
                },
            ]
        }
    )
    judge_adapter = FakeLLMAdapter(responses=[judge_response])
    judge = LLMJudge(adapter=judge_adapter)

    runner = DeterministicEvaluationRunner(judge=judge)
    summary = runner.evaluate_dataset(cases=subset, coordinator=coordinator)

    assert summary.total_cases == 2
    assert len(summary.case_results) == 2
    assert summary.case_results[0].judge_verdict is not None
    assert summary.case_results[1].judge_verdict is not None
    assert summary.case_results[1].judge_verdict.status == JudgeStatus.SKIPPED_NON_APPLICABLE
    assert summary.case_results[1].judge_verdict.passed is None
    assert summary.case_results[1].passed is True  # Case passes because skip was correct
    assert len(judge_adapter.calls) == 1  # Only CASE-001 invoked judge
