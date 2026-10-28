"""JSON Schema export utilities for inter-agent contracts."""

from typing import Any

from agent_eval_harness.contracts.handoff import OutreachHandoff
from agent_eval_harness.contracts.lead import LeadQualificationResult
from agent_eval_harness.contracts.lead_input import LeadInput
from agent_eval_harness.contracts.outreach import OutreachDraftResult


def export_json_schemas() -> dict[str, dict[str, Any]]:
    """Export standard JSON Schema definitions for all inter-agent contracts.

    Returns:
        Mapping of contract name to JSON Schema dictionary.
    """
    return {
        "LeadInput": LeadInput.model_json_schema(),
        "LeadQualificationResult": LeadQualificationResult.model_json_schema(),
        "OutreachHandoff": OutreachHandoff.model_json_schema(),
        "OutreachDraftResult": OutreachDraftResult.model_json_schema(),
    }
