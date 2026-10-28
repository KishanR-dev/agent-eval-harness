"""Exception hierarchy for agent-eval-harness."""


class HarnessError(Exception):
    """Base exception for all agent-eval-harness domain errors."""


class AdapterError(HarnessError):
    """Raised when an LLM adapter encounters an expected communication or provider error."""


class AgentExecutionError(HarnessError):
    """Raised when an agent execution fails due to contract validation or adapter error.

    Captures sanitized failure metadata without exposing secrets, API keys, or raw prompt bodies.
    """

    def __init__(
        self,
        stage: str,
        error_category: str,
        message: str,
        original_exception: Exception | None = None,
    ) -> None:
        super().__init__(f"[{stage}] {error_category}: {message}")
        self.stage = stage
        self.error_category = error_category
        self.message = message
        self.original_exception = original_exception


class FixtureNotFoundError(HarnessError):
    """Raised when a requested fixture file does not exist on disk."""


class FixtureCorruptedError(HarnessError):
    """Raised when a fixture file contains invalid JSON or violates the fixture schema."""


class FixtureExhaustedError(AdapterError):
    """Raised during replay when an agent requests more calls than recorded in the fixture."""


class BaselineUnavailableError(HarnessError):
    """Raised when a baseline comparison is requested in strict mode but no baseline is found."""


class BaselineIncompatibleError(HarnessError):
    """Raised when current evaluation run is incompatible with the reference baseline."""
