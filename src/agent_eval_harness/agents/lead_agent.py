"""Stage 1 Lead Qualification Agent."""

from pydantic import ValidationError

from agent_eval_harness.agents.base import BaseAgent, sanitize_validation_error
from agent_eval_harness.contracts.lead import LeadQualificationResult
from agent_eval_harness.contracts.lead_input import LeadInput
from agent_eval_harness.exceptions import AgentExecutionError

LEAD_AGENT_SYSTEM_PROMPT = (
    "You are an AI Lead Qualification Agent. Evaluate the inbound prospect information "
    "and return a single structured JSON object conforming strictly to the requested schema. "
    "Output raw JSON only without markdown formatting, code fences, or surrounding text."
)


class LeadQualificationAgent(BaseAgent):
    """Agent that assesses inbound lead inquiries against qualification criteria."""

    def qualify(self, lead_input: LeadInput) -> LeadQualificationResult:
        """Evaluate an inbound lead and produce structured qualification output.

        Args:
            lead_input: Validated inbound prospect context.

        Returns:
            Validated LeadQualificationResult.

        Raises:
            AgentExecutionError: On contract validation failure or expected adapter error.
        """
        emp_count = (
            str(lead_input.employee_count) if lead_input.employee_count is not None else "Unknown"
        )
        prompt = (
            f"Evaluate the following inbound lead:\n"
            f"- Lead ID: {lead_input.lead_id}\n"
            f"- Company Name: {lead_input.company_name}\n"
            f"- Industry: {lead_input.industry}\n"
            f"- Employee Count: {emp_count}\n"
            f"- Inbound Notes: {lead_input.notes}\n\n"
            "Produce a JSON object with fields:\n"
            "- schema_version (string, '1.0.0')\n"
            "- lead_id (string, matching input lead ID)\n"
            "- company_name (string)\n"
            "- industry (string)\n"
            "- qualification_status (string: 'QUALIFIED', 'DISQUALIFIED', or 'NEEDS_REVIEW')\n"
            "- fit_score (integer, 0 to 100)\n"
            "- summary (string explanation)\n"
            "- key_pain_points (list of strings)\n"
            "- recommended_angle (string or null)\n"
        )

        raw_response = self._execute_adapter(
            stage="lead_qualification",
            prompt=prompt,
            system_prompt=LEAD_AGENT_SYSTEM_PROMPT,
        )

        try:
            return LeadQualificationResult.model_validate_json(raw_response)
        except ValidationError as exc:
            sanitized = sanitize_validation_error(exc)
            raise AgentExecutionError(
                stage="lead_qualification",
                error_category="ContractValidationError",
                message=sanitized,
                original_exception=exc,
            ) from exc
