"""Base class and common helpers for agents."""

from pydantic import ValidationError

from agent_eval_harness.exceptions import AdapterError, AgentExecutionError
from agent_eval_harness.providers.base import LLMAdapter


def sanitize_validation_error(exc: ValidationError) -> str:
    """Format Pydantic ValidationError into a clean, sanitized summary.

    Avoids leaking environment dumps, raw prompt contents, or credentials.
    """
    error_items = exc.errors()
    formatted: list[str] = []
    for err in error_items:
        loc = ".".join(str(k) for k in err["loc"]) if err["loc"] else "root"
        formatted.append(f"{loc}: {err['msg']}")
    return "; ".join(formatted)


class BaseAgent:
    """Base class for harness agents with LLMAdapter injection."""

    def __init__(self, adapter: LLMAdapter) -> None:
        """Initialize agent with LLM provider adapter.

        Args:
            adapter: LLM provider adapter adhering to LLMAdapter protocol.
        """
        self.adapter = adapter

    def _execute_adapter(
        self,
        stage: str,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """Call the adapter, catching only expected AdapterError.

        Unexpected exceptions propagate uncaught.
        """
        try:
            return self.adapter.complete(prompt=prompt, system_prompt=system_prompt)
        except AdapterError as exc:
            raise AgentExecutionError(
                stage=stage,
                error_category="AdapterError",
                message=str(exc),
                original_exception=exc,
            ) from exc
