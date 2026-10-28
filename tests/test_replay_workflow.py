"""Integration tests executing workflow coordinator and runner via ReplayingLLMAdapter."""

from pathlib import Path

from agent_eval_harness.agents import LeadQualificationAgent, OutreachDrafterAgent
from agent_eval_harness.contracts import QualificationStatus
from agent_eval_harness.coordinator import CoordinatorStatus, WorkflowCoordinator
from agent_eval_harness.evaluation import DeterministicEvaluationRunner, JudgeStatus, LLMJudge
from agent_eval_harness.evaluation.dataset import load_dataset
from agent_eval_harness.providers import ReplayingLLMAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"


def test_replay_workflow_qualified_flow_e2e() -> None:
    """Coordinator executes full 2-stage qualified workflow entirely from canonical fixture."""
    fixture_path = FIXTURES_DIR / "qualified_workflow.json"
    adapter = ReplayingLLMAdapter.from_fixture_file(fixture_path, verify_stage=True)

    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    cases = load_dataset()
    case = cases[0]  # CASE-001 (Synthetix Cloud Systems)

    result = coordinator.run(lead_input=case.lead_input, outreach_config=case.outreach_config)

    # 1. Coordinator assertions
    assert result.status == CoordinatorStatus.COMPLETED
    assert result.lead_result is not None
    assert result.lead_result.qualification_status == QualificationStatus.QUALIFIED
    assert result.lead_result.fit_score == 88
    assert result.handoff is not None
    assert result.draft_result is not None
    assert result.draft_result.subject_line == "Accelerating SOC2 compliance for Synthetix Cloud"
    assert "SOC2" in result.draft_result.body

    # 2. Replay adapter consumption
    assert adapter.cursor == 2
    assert adapter.remaining_calls == 0
    assert len(adapter.calls) == 2

    # 3. Deterministic evaluation assertions
    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result)
    assert eval_res.passed is True
    assert eval_res.has_critical_failure is False
    assert eval_res.execution_status == CoordinatorStatus.COMPLETED


def test_replay_workflow_disqualified_flow_e2e() -> None:
    """Coordinator executes disqualified workflow; Stage 2 outreach is skipped cleanly."""
    fixture_path = FIXTURES_DIR / "disqualified_workflow.json"
    adapter = ReplayingLLMAdapter.from_fixture_file(fixture_path, verify_stage=True)

    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    cases = load_dataset()
    case = next(c for c in cases if c.case_id == "CASE-005")

    result = coordinator.run(lead_input=case.lead_input, outreach_config=case.outreach_config)

    # 1. Coordinator assertions
    assert result.status == CoordinatorStatus.SKIPPED_DISQUALIFIED
    assert result.lead_result is not None
    assert result.lead_result.qualification_status == QualificationStatus.DISQUALIFIED
    assert result.lead_result.fit_score == 12
    assert result.handoff is None
    assert result.draft_result is None

    # 2. Replay adapter consumption (only 1 call consumed; Stage 2 was not invoked)
    assert adapter.cursor == 1
    assert adapter.remaining_calls == 0
    assert len(adapter.calls) == 1

    # 3. Deterministic evaluation assertions
    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result)
    assert eval_res.passed is True
    assert eval_res.has_critical_failure is False


def test_replay_workflow_provider_error_e2e() -> None:
    """Stage 2 provider failure raises AdapterError, preserving Stage 1 qualification results."""
    fixture_path = FIXTURES_DIR / "provider_error_workflow.json"
    adapter = ReplayingLLMAdapter.from_fixture_file(fixture_path, verify_stage=True)

    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    cases = load_dataset()
    case = cases[0]

    result = coordinator.run(lead_input=case.lead_input, outreach_config=case.outreach_config)

    # 1. Coordinator assertions: Stage 2 failed, Stage 1 result is preserved
    assert result.status == CoordinatorStatus.FAILED
    assert result.failed_stage == "outreach_drafting"
    assert result.error_category == "AdapterError"
    assert "Simulated upstream 503" in (result.error_message or "")
    assert result.lead_result is not None
    assert result.lead_result.qualification_status == QualificationStatus.QUALIFIED
    assert result.lead_result.fit_score == 88
    assert result.handoff is not None
    assert result.draft_result is None

    # 2. Adapter state: both exchanges consumed (Stage 1 succeeded, Stage 2 raised error)
    assert adapter.cursor == 2
    assert adapter.remaining_calls == 0
    assert len(adapter.calls) == 2

    # 3. Deterministic evaluation assertions: FAILED status unconditionally fails case
    runner = DeterministicEvaluationRunner()
    eval_res = runner.evaluate_result(case=case, result=result)
    assert eval_res.passed is False


def test_replay_with_judge_integration() -> None:
    """Three-tier workflow + judge fixture executes and grades correctly entirely from disk."""
    fixture_path = FIXTURES_DIR / "workflow_with_judge.json"
    adapter = ReplayingLLMAdapter.from_fixture_file(fixture_path, verify_stage=True)

    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)
    judge = LLMJudge(adapter=adapter)

    cases = load_dataset()
    case = cases[0]

    # Run workflow (consumes exchanges 0 and 1: lead qualification and outreach drafting)
    result = coordinator.run(lead_input=case.lead_input, outreach_config=case.outreach_config)
    assert result.status == CoordinatorStatus.COMPLETED
    assert adapter.cursor == 2
    assert adapter.remaining_calls == 1

    # Run evaluation with judge (consumes exchange 2: judge evaluation)
    runner = DeterministicEvaluationRunner(judge=judge)
    eval_res = runner.evaluate_result(case=case, result=result)

    assert adapter.cursor == 3
    assert adapter.remaining_calls == 0
    assert eval_res.passed is True
    assert eval_res.judge_verdict is not None
    assert eval_res.judge_verdict.status == JudgeStatus.COMPLETED_PASS
    assert eval_res.judge_verdict.overall_score == 4.0
