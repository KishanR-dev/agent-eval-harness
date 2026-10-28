"""Unit tests for LeadQualificationAgent and OutreachDrafterAgent."""

import json
from typing import Any

import pytest

from agent_eval_harness.agents import LeadQualificationAgent, OutreachDrafterAgent
from agent_eval_harness.contracts import (
    LeadInput,
    OutreachChannel,
    OutreachDraftResult,
    OutreachHandoff,
    QualificationStatus,
)
from agent_eval_harness.exceptions import AdapterError, AgentExecutionError
from agent_eval_harness.providers import FakeLLMAdapter


def test_lead_agent_success(
    valid_lead_input: LeadInput,
    valid_lead_json: str,
) -> None:
    """LeadQualificationAgent parses valid JSON into LeadQualificationResult."""
    adapter = FakeLLMAdapter(responses=[valid_lead_json])
    agent = LeadQualificationAgent(adapter=adapter)

    result = agent.qualify(valid_lead_input)
    assert result.lead_id == "lead_synth_101"
    assert result.qualification_status == QualificationStatus.QUALIFIED
    assert result.fit_score == 85
    assert len(adapter.calls) == 1
    assert "Synthetix Dynamics Ltd" in adapter.calls[0].prompt


def test_lead_agent_malformed_json(valid_lead_input: LeadInput) -> None:
    """LeadQualificationAgent raises AgentExecutionError on malformed JSON."""
    adapter = FakeLLMAdapter(responses=["Not valid json at all {"])
    agent = LeadQualificationAgent(adapter=adapter)

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.qualify(valid_lead_input)

    err = exc_info.value
    assert err.stage == "lead_qualification"
    assert err.error_category == "ContractValidationError"
    assert "JSON decode error" in err.message or "Invalid JSON" in err.message


def test_lead_agent_schema_violation(
    valid_lead_input: LeadInput,
    valid_lead_payload: dict[str, Any],
) -> None:
    """LeadQualificationAgent raises AgentExecutionError on extra unmodeled fields."""
    payload = dict(valid_lead_payload)
    payload["unauthorized_field"] = "leak"
    adapter = FakeLLMAdapter(responses=[json.dumps(payload)])
    agent = LeadQualificationAgent(adapter=adapter)

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.qualify(valid_lead_input)

    err = exc_info.value
    assert err.stage == "lead_qualification"
    assert err.error_category == "ContractValidationError"
    assert "unauthorized_field" in err.message


def test_lead_agent_adapter_error(valid_lead_input: LeadInput) -> None:
    """LeadQualificationAgent wraps AdapterError into AgentExecutionError."""
    adapter = FakeLLMAdapter(exception_to_raise=AdapterError("Simulated provider rate limit"))
    agent = LeadQualificationAgent(adapter=adapter)

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.qualify(valid_lead_input)

    err = exc_info.value
    assert err.stage == "lead_qualification"
    assert err.error_category == "AdapterError"
    assert "Simulated provider rate limit" in err.message


def test_lead_agent_unexpected_exception_propagates(valid_lead_input: LeadInput) -> None:
    """Unexpected exceptions are not swallowed by LeadQualificationAgent."""
    adapter = FakeLLMAdapter(exception_to_raise=KeyError("Uncaught system key error"))
    agent = LeadQualificationAgent(adapter=adapter)

    with pytest.raises(KeyError) as exc_info:
        agent.qualify(valid_lead_input)
    assert "Uncaught system key error" in str(exc_info.value)


def test_outreach_agent_success_email(
    valid_handoff_result: OutreachHandoff,
    valid_email_draft_json: str,
) -> None:
    """OutreachDrafterAgent parses valid email draft with subject line."""
    adapter = FakeLLMAdapter(responses=[valid_email_draft_json])
    agent = OutreachDrafterAgent(adapter=adapter)

    result = agent.draft(valid_handoff_result)
    assert isinstance(result, OutreachDraftResult)
    assert result.channel == OutreachChannel.EMAIL
    assert result.subject_line is not None
    assert result.word_count > 0
    assert len(adapter.calls) == 1
    assert "EMAIL" in adapter.calls[0].prompt


def test_outreach_agent_success_linkedin(
    valid_handoff_result: OutreachHandoff,
    valid_linkedin_draft_json: str,
) -> None:
    """OutreachDrafterAgent parses valid LinkedIn draft with None subject line."""
    # Create handoff configured for LinkedIn
    li_handoff = OutreachHandoff(
        lead=valid_handoff_result.lead,
        channel=OutreachChannel.LINKEDIN,
        target_persona="VP of Infrastructure",
        max_words=100,
    )
    adapter = FakeLLMAdapter(responses=[valid_linkedin_draft_json])
    agent = OutreachDrafterAgent(adapter=adapter)

    result = agent.draft(li_handoff)
    assert result.channel == OutreachChannel.LINKEDIN
    assert result.subject_line is None


def test_outreach_agent_channel_violation(
    valid_handoff_result: OutreachHandoff,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """OutreachDrafterAgent raises AgentExecutionError when email omits subject line."""
    payload = dict(valid_email_draft_payload)
    payload["subject_line"] = None
    adapter = FakeLLMAdapter(responses=[json.dumps(payload)])
    agent = OutreachDrafterAgent(adapter=adapter)

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.draft(valid_handoff_result)

    err = exc_info.value
    assert err.stage == "outreach_drafting"
    assert err.error_category == "ContractValidationError"
    assert "subject_line is required for EMAIL channel" in err.message


def test_outreach_agent_adapter_error(valid_handoff_result: OutreachHandoff) -> None:
    """OutreachDrafterAgent wraps AdapterError into AgentExecutionError."""
    adapter = FakeLLMAdapter(exception_to_raise=AdapterError("Network connection reset"))
    agent = OutreachDrafterAgent(adapter=adapter)

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.draft(valid_handoff_result)

    err = exc_info.value
    assert err.stage == "outreach_drafting"
    assert err.error_category == "AdapterError"
    assert "Network connection reset" in err.message


def test_outreach_agent_unexpected_exception_propagates(
    valid_handoff_result: OutreachHandoff,
) -> None:
    """Unexpected exceptions are not swallowed by OutreachDrafterAgent."""
    adapter = FakeLLMAdapter(exception_to_raise=TypeError("Unexpected type error in adapter"))
    agent = OutreachDrafterAgent(adapter=adapter)

    with pytest.raises(TypeError) as exc_info:
        agent.draft(valid_handoff_result)
    assert "Unexpected type error in adapter" in str(exc_info.value)
