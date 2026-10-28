"""Deterministic fake LLM adapter for offline unit and integration testing."""

from agent_eval_harness.providers.base import AdapterCall, LLMAdapter


class FakeLLMAdapter(LLMAdapter):
    """Deterministic offline adapter yielding canned FIFO responses or injected exceptions."""

    def __init__(
        self,
        responses: list[str] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        """Initialize FakeLLMAdapter.

        Args:
            responses: Sequence of response strings to yield in FIFO order.
            exception_to_raise: Optional exception to raise on complete().
        """
        self._responses: list[str] = list(responses) if responses is not None else []
        self._exception_to_raise = exception_to_raise
        self.calls: list[AdapterCall] = []

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Record the call and return next queued response or raise queued exception."""
        self.calls.append(AdapterCall(prompt=prompt, system_prompt=system_prompt))

        if self._exception_to_raise is not None:
            raise self._exception_to_raise

        if not self._responses:
            raise RuntimeError("FakeLLMAdapter response queue exhausted: no responses remaining.")

        return self._responses.pop(0)
