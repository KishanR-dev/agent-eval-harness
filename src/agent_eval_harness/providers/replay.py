"""Provider adapter for deterministic replay of recorded fixture exchanges."""

import json
from pathlib import Path

from pydantic import ValidationError

from agent_eval_harness.exceptions import (
    AdapterError,
    FixtureCorruptedError,
    FixtureExhaustedError,
    FixtureNotFoundError,
)
from agent_eval_harness.fixtures.models import ExchangeStage, ReplayFixture
from agent_eval_harness.providers.base import AdapterCall, LLMAdapter


class ReplayingLLMAdapter(LLMAdapter):
    """Deterministic adapter that sequentially replays recorded fixture exchanges."""

    def __init__(self, fixture: ReplayFixture, verify_stage: bool = True) -> None:
        """Initialize ReplayingLLMAdapter with a validated ReplayFixture.

        Args:
            fixture: The ReplayFixture holding sequential exchanges.
            verify_stage: Whether to verify incoming prompt stage against recorded exchange stage.
        """
        self.fixture = fixture
        self.verify_stage = verify_stage
        self.calls: list[AdapterCall] = []
        self._cursor: int = 0

    @classmethod
    def from_fixture_file(
        cls,
        path: Path | str,
        verify_stage: bool = True,
    ) -> "ReplayingLLMAdapter":
        """Load and validate a replay fixture from a JSON file.

        Args:
            path: File path to the JSON fixture.
            verify_stage: Whether to enable stage verification during replay.

        Returns:
            Configured ReplayingLLMAdapter instance.

        Raises:
            FixtureNotFoundError: If the fixture file does not exist.
            FixtureCorruptedError: If JSON parsing or Pydantic validation fails.
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise FixtureNotFoundError(f"Fixture file not found: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as err:
            raise FixtureCorruptedError(
                f"Failed to read or parse fixture JSON from '{file_path}': {err}"
            ) from err

        try:
            fixture = ReplayFixture.model_validate(data)
        except ValidationError as err:
            raise FixtureCorruptedError(
                f"Fixture validation failed for '{file_path}': {err}"
            ) from err

        return cls(fixture=fixture, verify_stage=verify_stage)

    @property
    def cursor(self) -> int:
        """Index of the next exchange to be emitted."""
        return self._cursor

    @property
    def remaining_calls(self) -> int:
        """Number of recorded exchanges remaining for replay."""
        return max(0, len(self.fixture.exchanges) - self._cursor)

    def reset(self) -> None:
        """Reset the replay cursor and clear call history."""
        self._cursor = 0
        self.calls.clear()

    @staticmethod
    def _detect_stage(prompt: str, system_prompt: str | None) -> ExchangeStage | None:
        """Detect workflow stage from prompt signatures without altering adapter interface."""
        combined = f"{system_prompt or ''}\n{prompt}"
        if (
            "Lead Qualification Agent" in combined
            or "Evaluate the following inbound lead:" in combined
        ):
            return ExchangeStage.LEAD_QUALIFICATION
        if (
            "Outreach Drafting Agent" in combined
            or "Draft an outreach message based on this handoff:" in combined
        ):
            return ExchangeStage.OUTREACH_DRAFTING
        if "expert evaluator" in combined or "<untrusted_evaluated_content>" in combined:
            return ExchangeStage.JUDGE
        return None

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Yield the next recorded response in sequential FIFO order.

        Args:
            prompt: User-level instruction or payload.
            system_prompt: Optional system-level prompt.

        Returns:
            The recorded response text.

        Raises:
            FixtureExhaustedError: If called after all recorded exchanges are consumed.
            AdapterError: If stage mismatch occurs or exchange simulates a provider failure.
        """
        self.calls.append(AdapterCall(prompt=prompt, system_prompt=system_prompt))

        if self._cursor >= len(self.fixture.exchanges):
            raise FixtureExhaustedError(
                f"Replay fixture '{self.fixture.fixture_id}' exhausted: "
                f"call index {self._cursor} exceeded {len(self.fixture.exchanges)} "
                f"recorded exchanges."
            )

        exchange = self.fixture.exchanges[self._cursor]

        # Stage consistency check
        if self.verify_stage:
            detected_stage = self._detect_stage(prompt, system_prompt)
            if detected_stage != exchange.stage:
                detected_label = detected_stage.value if detected_stage else "unknown"
                raise AdapterError(
                    f"Replay stage mismatch at call {self._cursor}: fixture expected "
                    f"'{exchange.stage.value}', but detected '{detected_label}'."
                )

        self._cursor += 1

        # Simulated provider error
        if exchange.error_to_raise is not None:
            raise AdapterError(exchange.error_to_raise)

        assert exchange.response_text is not None  # Guaranteed by schema validator
        return exchange.response_text
