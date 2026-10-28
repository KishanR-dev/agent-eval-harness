"""Unit and integration tests for WorkflowCoordinator and state invariants."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_eval_harness.agents import LeadQualificationAgent, OutreachDrafterAgent
from agent_eval_harness.contracts import (
    LeadInput,
    OutreachChannel,
    OutreachTone,
    QualificationStatus,
)
from agent_eval_harness.coordinator import (
    CoordinatorResult,
    CoordinatorStatus,
    OutreachConfig,
    WorkflowCoordinator,
)
from agent_eval_harness.exceptions import AdapterError
from agent_eval_harness.providers import FakeLLMAdapter


def test_coordinator_completed_workflow(
    valid_lead_input: LeadInput,
    valid_lead_json: str,
    valid_email_draft_json: str,
) -> None:
    """Qualified lead runs Stage 1 -> Handoff -> Stage 2 returning COMPLETED with all artifacts."""
    adapter = FakeLLMAdapter(responses=[valid_lead_json, valid_email_draft_json])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    outreach_config = OutreachConfig(
        channel=OutreachChannel.EMAIL,
        target_persona="VP of Infrastructure",
        tone_preference=OutreachTone.CONSULTATIVE,
        max_words=120,
    )

    result = coordinator.run(valid_lead_input, outreach_config=outreach_config)

    # State invariant checks for COMPLETED
    assert result.status == CoordinatorStatus.COMPLETED
    assert result.lead_result is not None
    assert result.lead_result.is_qualified is True
    assert result.handoff is not None
    assert result.handoff.channel == OutreachChannel.EMAIL
    assert result.draft_result is not None
    assert result.draft_result.word_count > 0
    assert result.failed_stage is None
    assert result.error_category is None
    assert result.error_message is None

    # Sequencing check: both stages invoked in order
    assert len(adapter.calls) == 2
    assert "Evaluate the following inbound lead" in adapter.calls[0].prompt
    assert "Draft an outreach message" in adapter.calls[1].prompt


def test_coordinator_disqualified_skips_stage2(
    valid_lead_input: LeadInput,
    disqualified_lead_json: str,
) -> None:
    """Disqualified lead halts cleanly with SKIPPED_DISQUALIFIED and never calls Stage 2."""
    adapter = FakeLLMAdapter(responses=[disqualified_lead_json])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    result = coordinator.run(valid_lead_input)

    # State invariant checks for SKIPPED_DISQUALIFIED
    assert result.status == CoordinatorStatus.SKIPPED_DISQUALIFIED
    assert result.lead_result is not None
    assert result.lead_result.qualification_status == QualificationStatus.DISQUALIFIED
    assert result.handoff is None
    assert result.draft_result is None
    assert result.failed_stage is None
    assert result.error_category is None
    assert result.error_message is None

    # Crucial assertion: Stage 2 outreach was never invoked
    assert len(adapter.calls) == 1


def test_coordinator_needs_review_skips_stage2(
    valid_lead_input: LeadInput,
    needs_review_lead_json: str,
) -> None:
    """Needs-review lead halts cleanly with SKIPPED_NEEDS_REVIEW and never calls Stage 2."""
    adapter = FakeLLMAdapter(responses=[needs_review_lead_json])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    result = coordinator.run(valid_lead_input)

    # State invariant checks for SKIPPED_NEEDS_REVIEW
    assert result.status == CoordinatorStatus.SKIPPED_NEEDS_REVIEW
    assert result.lead_result is not None
    assert result.lead_result.qualification_status == QualificationStatus.NEEDS_REVIEW
    assert result.handoff is None
    assert result.draft_result is None
    assert result.failed_stage is None
    assert result.error_category is None
    assert result.error_message is None

    # Crucial assertion: Stage 2 outreach was never invoked
    assert len(adapter.calls) == 1


def test_coordinator_stage1_failure_prevents_stage2(
    valid_lead_input: LeadInput,
) -> None:
    """Stage 1 contract failure produces FAILED status and prevents Stage 2 invocation."""
    adapter = FakeLLMAdapter(responses=["Malformed non-JSON output"])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    result = coordinator.run(valid_lead_input)

    assert result.status == CoordinatorStatus.FAILED
    assert result.failed_stage == "lead_qualification"
    assert result.error_category == "ContractValidationError"
    assert result.error_message is not None
    assert result.lead_result is None
    assert result.handoff is None
    assert result.draft_result is None

    # Stage 2 was never invoked
    assert len(adapter.calls) == 1


def test_coordinator_stage2_failure_preserves_lead_and_handoff(
    valid_lead_input: LeadInput,
    valid_lead_json: str,
) -> None:
    """Stage 2 failure produces FAILED status but preserves valid Stage 1 lead and handoff."""
    adapter = FakeLLMAdapter(responses=[valid_lead_json, "Malformed draft output"])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    result = coordinator.run(valid_lead_input)

    assert result.status == CoordinatorStatus.FAILED
    assert result.failed_stage == "outreach_drafting"
    assert result.error_category == "ContractValidationError"
    assert result.error_message is not None

    # Intermediate state preservation
    assert result.lead_result is not None
    assert result.lead_result.is_qualified is True
    assert result.handoff is not None
    assert result.draft_result is None

    assert len(adapter.calls) == 2


def test_coordinator_handoff_construction_failure_preserves_lead(
    valid_lead_input: LeadInput,
    valid_lead_json: str,
) -> None:
    """Invalid handoff configuration fails at handoff_construction and prevents Stage 2."""
    adapter = FakeLLMAdapter(responses=[valid_lead_json])
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    # Create config that will violate OutreachHandoff constraints (e.g. max_words < 10)
    # OutreachConfig allows max_words >= 10, so construct an invalid config bypassing or testing
    # Note: OutreachConfig itself enforces ge=10; if target_persona is whitespace:
    bad_config = OutreachConfig.model_construct(
        channel=OutreachChannel.EMAIL,
        target_persona="   ",  # Fails OutreachHandoff non-empty validator
        tone_preference=OutreachTone.PROFESSIONAL,
        max_words=150,
        constraints=[],
    )

    result = coordinator.run(valid_lead_input, outreach_config=bad_config)

    assert result.status == CoordinatorStatus.FAILED
    assert result.failed_stage == "handoff_construction"
    assert result.error_category == "ContractValidationError"
    assert "target_persona must not be empty" in str(result.error_message)

    # Lead result is preserved; draft is None; Stage 2 was not called
    assert result.lead_result is not None
    assert result.handoff is None
    assert result.draft_result is None
    assert len(adapter.calls) == 1


def test_coordinator_adapter_error_in_stage1(
    valid_lead_input: LeadInput,
) -> None:
    """Expected AdapterError in Stage 1 produces FAILED status with AdapterError category."""
    adapter = FakeLLMAdapter(exception_to_raise=AdapterError("Simulated provider timeout"))
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    result = coordinator.run(valid_lead_input)

    assert result.status == CoordinatorStatus.FAILED
    assert result.failed_stage == "lead_qualification"
    assert result.error_category == "AdapterError"
    assert "Simulated provider timeout" in str(result.error_message)
    assert result.lead_result is None


def test_coordinator_unexpected_exception_propagates(
    valid_lead_input: LeadInput,
) -> None:
    """Unexpected exceptions (e.g. RuntimeError, TypeError) are never swallowed."""
    adapter = FakeLLMAdapter(exception_to_raise=RuntimeError("System hardware fault"))
    lead_agent = LeadQualificationAgent(adapter=adapter)
    outreach_agent = OutreachDrafterAgent(adapter=adapter)
    coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

    with pytest.raises(RuntimeError) as exc_info:
        coordinator.run(valid_lead_input)
    assert "System hardware fault" in str(exc_info.value)


# ============================================================================
# Model-level State Invariant Tests on CoordinatorResult
# ============================================================================


def test_coordinator_result_invariant_completed_validation(
    valid_lead_result: Any,
    valid_handoff_result: Any,
    valid_email_draft_result: Any,
) -> None:
    """CoordinatorResult rejects COMPLETED if artifacts missing or failure fields present."""
    with pytest.raises(ValidationError):
        CoordinatorResult(status=CoordinatorStatus.COMPLETED)

    # COMPLETED must not have failure fields
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.COMPLETED,
            lead_result=valid_lead_result,
            handoff=valid_handoff_result,
            draft_result=valid_email_draft_result,
            failed_stage="lead_qualification",
            error_category="Error",
            error_message="msg",
        )


def test_coordinator_result_invariant_skipped_disqualified(
    valid_lead_result: Any,
    valid_disqualified_lead_result: Any,
    valid_handoff_result: Any,
) -> None:
    """CoordinatorResult enforces SKIPPED_DISQUALIFIED invariants."""
    # Lead is qualified but status is SKIPPED_DISQUALIFIED
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
            lead_result=valid_lead_result,  # status is QUALIFIED
        )

    # Disqualified lead with handoff attached
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
            lead_result=valid_disqualified_lead_result,
            handoff=valid_handoff_result,
        )

    # Disqualified lead with failure fields attached
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
            lead_result=valid_disqualified_lead_result,
            failed_stage="lead_qualification",
            error_category="SomeError",
            error_message="msg",
        )


def test_coordinator_result_invariant_skipped_needs_review(
    valid_lead_result: Any,
    valid_needs_review_lead_result: Any,
    valid_handoff_result: Any,
) -> None:
    """CoordinatorResult enforces SKIPPED_NEEDS_REVIEW invariants."""
    # Missing lead result or wrong status
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_NEEDS_REVIEW,
            lead_result=valid_lead_result,
        )

    # Needs review with handoff attached
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_NEEDS_REVIEW,
            lead_result=valid_needs_review_lead_result,
            handoff=valid_handoff_result,
        )

    # Needs review with failure fields attached
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.SKIPPED_NEEDS_REVIEW,
            lead_result=valid_needs_review_lead_result,
            failed_stage="lead_qualification",
            error_category="SomeError",
            error_message="msg",
        )


def test_coordinator_result_invariant_failed_validation(
    valid_email_draft_result: Any,
) -> None:
    """CoordinatorResult rejects FAILED if failure fields are omitted or draft is populated."""
    # Missing failure fields
    with pytest.raises(ValidationError):
        CoordinatorResult(status=CoordinatorStatus.FAILED)

    # FAILED must not have draft_result
    with pytest.raises(ValidationError):
        CoordinatorResult(
            status=CoordinatorStatus.FAILED,
            failed_stage="lead_qualification",
            error_category="Error",
            error_message="msg",
            draft_result=valid_email_draft_result,
        )

    # Valid FAILED construction succeeds
    valid_failed = CoordinatorResult(
        status=CoordinatorStatus.FAILED,
        failed_stage="lead_qualification",
        error_category="Error",
        error_message="msg",
    )
    assert valid_failed.status == CoordinatorStatus.FAILED
