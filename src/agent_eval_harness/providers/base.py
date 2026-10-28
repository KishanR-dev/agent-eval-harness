"""Abstract interface for LLM provider adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from agent_eval_harness.exceptions import AdapterError

__all__ = ["LLMAdapter", "AdapterCall", "AdapterError"]


@dataclass(frozen=True)
class AdapterCall:
    """Record of an invocation made to an LLMAdapter."""

    prompt: str
    system_prompt: str | None = None


class LLMAdapter(ABC):
    """Abstract interface isolating LLM provider mechanics from agent logic."""

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate text completion from a prompt and optional system prompt.

        Args:
            prompt: User-level instruction or formatted payload.
            system_prompt: Optional system-level instruction.

        Returns:
            Raw string completion from the model.

        Raises:
            AdapterError: On expected provider/communication failures.
        """
