"""Pytest configuration and synthetic fixtures for contract testing.

All data is strictly fictional/synthetic to ensure safe, reproducible tests
with zero credentials or real personal/company identifiers.
"""

import json
from typing import Any

import pytest

from agent_eval_harness.contracts import (
    LeadInput,
    LeadQualificationResult,
    OutreachDraftResult,
    OutreachHandoff,
)


@pytest.fixture
def valid_lead_input_payload() -> dict[str, Any]:
    """Return a valid synthetic payload for LeadInput."""
    return {
        "schema_version": "1.0.0",
        "lead_id": "lead_synth_101",
        "company_name": "Synthetix Dynamics Ltd",
        "industry": "Enterprise Cloud Infrastructure",
        "notes": (
            "Inbound inquiry requesting automated policy review and cost reduction options "
            "for multi-cloud Kubernetes clusters."
        ),
        "employee_count": 250,
    }


@pytest.fixture
def valid_lead_input(valid_lead_input_payload: dict[str, Any]) -> LeadInput:
    """Return an instantiated LeadInput model."""
    return LeadInput.model_validate(valid_lead_input_payload)


@pytest.fixture
def valid_lead_payload() -> dict[str, Any]:
    """Return a valid synthetic payload for LeadQualificationResult."""
    return {
        "schema_version": "1.0.0",
        "lead_id": "lead_synth_101",
        "company_name": "Synthetix Dynamics Ltd",
        "industry": "Enterprise Cloud Infrastructure",
        "qualification_status": "QUALIFIED",
        "fit_score": 85,
        "summary": "Demonstrates high demand for automated cloud governance solutions.",
        "key_pain_points": [
            "Excessive compute expenditures",
            "Slow manual security compliance reviews",
        ],
        "recommended_angle": "Highlight automated policy enforcement to cut audit time.",
    }


@pytest.fixture
def valid_lead_result(valid_lead_payload: dict[str, Any]) -> LeadQualificationResult:
    """Return an instantiated LeadQualificationResult model."""
    return LeadQualificationResult.model_validate(valid_lead_payload)


@pytest.fixture
def valid_handoff_payload(valid_lead_payload: dict[str, Any]) -> dict[str, Any]:
    """Return a valid synthetic payload for OutreachHandoff."""
    return {
        "schema_version": "1.0.0",
        "lead": valid_lead_payload,
        "channel": "EMAIL",
        "target_persona": "VP of Infrastructure Engineering",
        "tone_preference": "CONSULTATIVE",
        "max_words": 120,
        "constraints": [
            "Do not quote fixed pricing",
            "Reference SOC2 compliance acceleration",
        ],
    }


@pytest.fixture
def valid_handoff_result(valid_handoff_payload: dict[str, Any]) -> OutreachHandoff:
    """Return an instantiated OutreachHandoff model."""
    return OutreachHandoff.model_validate(valid_handoff_payload)


@pytest.fixture
def valid_email_draft_payload() -> dict[str, Any]:
    """Return a valid synthetic payload for an email OutreachDraftResult."""
    return {
        "schema_version": "1.0.0",
        "lead_id": "lead_synth_101",
        "channel": "EMAIL",
        "subject_line": "Accelerating cloud compliance for Synthetix Dynamics",
        "body": (
            "Hi team, noticed your recent expansion into multi-cloud infrastructure. "
            "Many infrastructure teams face compliance review bottlenecks as environments scale. "
            "Our automated policy engine ensures audit readiness without slowing release velocity."
        ),
        "call_to_action": "Would you have 15 minutes next Tuesday for a brief walkthrough?",
        "disclaimers_included": ["Reply unsubscribe to opt out."],
    }


@pytest.fixture
def valid_linkedin_draft_payload() -> dict[str, Any]:
    """Return a valid synthetic payload for a LinkedIn OutreachDraftResult."""
    return {
        "schema_version": "1.0.0",
        "lead_id": "lead_synth_101",
        "channel": "LINKEDIN",
        "subject_line": None,
        "body": (
            "Hi, saw your team is expanding cloud infrastructure. We built an automated engine "
            "that streamlines audit readiness for engineering teams."
        ),
        "call_to_action": "Open to connecting and sharing a quick case study?",
        "disclaimers_included": [],
    }


@pytest.fixture
def valid_lead_json(valid_lead_payload: dict[str, Any]) -> str:
    """Return JSON string for valid qualified lead."""
    return json.dumps(valid_lead_payload)


@pytest.fixture
def disqualified_lead_json(valid_lead_payload: dict[str, Any]) -> str:
    """Return JSON string for disqualified lead."""
    p = dict(valid_lead_payload)
    p["qualification_status"] = "DISQUALIFIED"
    p["fit_score"] = 15
    p["summary"] = "Inquiry is from a hobbyist outside target enterprise market."
    return json.dumps(p)


@pytest.fixture
def needs_review_lead_json(valid_lead_payload: dict[str, Any]) -> str:
    """Return JSON string for needs-review lead."""
    p = dict(valid_lead_payload)
    p["qualification_status"] = "NEEDS_REVIEW"
    p["fit_score"] = 50
    p["summary"] = "Enterprise lead but requirements span multiple incompatible legacy systems."
    return json.dumps(p)


@pytest.fixture
def valid_email_draft_json(valid_email_draft_payload: dict[str, Any]) -> str:
    """Return JSON string for valid email draft."""
    return json.dumps(valid_email_draft_payload)


@pytest.fixture
def valid_linkedin_draft_json(valid_linkedin_draft_payload: dict[str, Any]) -> str:
    """Return JSON string for valid LinkedIn draft."""
    return json.dumps(valid_linkedin_draft_payload)


@pytest.fixture
def valid_email_draft_result(valid_email_draft_payload: dict[str, Any]) -> OutreachDraftResult:
    """Return an instantiated OutreachDraftResult model."""
    return OutreachDraftResult.model_validate(valid_email_draft_payload)


@pytest.fixture
def valid_disqualified_lead_result(disqualified_lead_json: str) -> LeadQualificationResult:
    """Return an instantiated disqualified LeadQualificationResult."""
    return LeadQualificationResult.model_validate_json(disqualified_lead_json)


@pytest.fixture
def valid_needs_review_lead_result(needs_review_lead_json: str) -> LeadQualificationResult:
    """Return an instantiated needs-review LeadQualificationResult."""
    return LeadQualificationResult.model_validate_json(needs_review_lead_json)
