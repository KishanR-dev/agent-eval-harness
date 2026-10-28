"""Stage 2 Outreach Drafting Agent."""

from pydantic import ValidationError

from agent_eval_harness.agents.base import BaseAgent, sanitize_validation_error
from agent_eval_harness.contracts.handoff import OutreachChannel, OutreachHandoff
from agent_eval_harness.contracts.outreach import OutreachDraftResult
from agent_eval_harness.exceptions import AgentExecutionError

OUTREACH_AGENT_SYSTEM_PROMPT = (
    "You are an AI Outreach Drafting Agent. Draft a tailored outreach message based on the "
    "provided qualified lead context and drafting constraints. Return a single structured JSON "
    "object conforming strictly to the requested schema. Output raw JSON only without markdown "
    "formatting, code fences, or surrounding text."
)


class OutreachDrafterAgent(BaseAgent):
    """Agent that creates constrained outreach drafts from validated handoff contracts."""

    def draft(self, handoff: OutreachHandoff) -> OutreachDraftResult:
        """Generate a tailored outreach message draft from a validated handoff.

        Args:
            handoff: Validated inter-agent handoff payload.

        Returns:
            Validated OutreachDraftResult.

        Raises:
            AgentExecutionError: On contract validation failure or expected adapter error.
        """
        constraints_desc = (
            "\n".join(f"- {c}" for c in handoff.constraints) if handoff.constraints else "None"
        )
        subject_instruction = (
            "Must provide a compelling non-empty subject_line."
            if handoff.channel == OutreachChannel.EMAIL
            else "Must set subject_line to null (LinkedIn DMs do not use subject lines)."
        )
        rec_angle = handoff.lead.recommended_angle or "Standard value proposition"
        pain_points = (
            ", ".join(handoff.lead.key_pain_points) if handoff.lead.key_pain_points else "None"
        )

        prompt = (
            f"Draft an outreach message with the following context and constraints:\n"
            f"- Lead ID: {handoff.lead.lead_id}\n"
            f"- Company: {handoff.lead.company_name} ({handoff.lead.industry})\n"
            f"- Target Persona: {handoff.target_persona}\n"
            f"- Channel: {handoff.channel.value}\n"
            f"- Tone: {handoff.tone_preference.value}\n"
            f"- Max Word Count Ceiling: {handoff.max_words}\n"
            f"- Recommended Angle: {rec_angle}\n"
            f"- Key Pain Points: {pain_points}\n"
            f"- Constraints & Forbidden Terms:\n{constraints_desc}\n\n"
            f"Produce a JSON object with fields:\n"
            f"- schema_version (string, '1.0.0')\n"
            f"- lead_id (string, matching {handoff.lead.lead_id})\n"
            f"- channel (string, '{handoff.channel.value}')\n"
            f"- subject_line (string or null: {subject_instruction})\n"
            f"- body (string, message body text within {handoff.max_words} words)\n"
            f"- call_to_action (string, specific next step ask)\n"
            f"- disclaimers_included (list of strings)\n"
        )

        raw_response = self._execute_adapter(
            stage="outreach_drafting",
            prompt=prompt,
            system_prompt=OUTREACH_AGENT_SYSTEM_PROMPT,
        )

        try:
            return OutreachDraftResult.model_validate_json(raw_response)
        except ValidationError as exc:
            sanitized = sanitize_validation_error(exc)
            raise AgentExecutionError(
                stage="outreach_drafting",
                error_category="ContractValidationError",
                message=sanitized,
                original_exception=exc,
            ) from exc
