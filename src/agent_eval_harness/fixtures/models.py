"""Strict Pydantic v2 contracts for replay fixtures."""

import re
from enum import StrEnum

from pydantic import Field, model_validator

from agent_eval_harness.contracts.base import (
    CURRENT_SCHEMA_VERSION,
    StrictBaseModel,
    SupportedSchemaVersion,
)

# Common credential patterns for safeguard scanning (not an exhaustive detector)
CREDENTIAL_PATTERN = re.compile(
    r"\b(?:sk-[a-zA-Z0-9]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]{20,}|ghp_[a-zA-Z0-9]{20,})\b"
)


class ExchangeStage(StrEnum):
    """Supported agent workflow and evaluation stages for recorded exchanges."""

    LEAD_QUALIFICATION = "lead_qualification"
    OUTREACH_DRAFTING = "outreach_drafting"
    JUDGE = "judge"


class RecordedExchange(StrictBaseModel):
    """A single recorded exchange within a replay fixture."""

    call_index: int = Field(..., ge=0, description="0-indexed sequence position")
    stage: ExchangeStage = Field(..., strict=False, description="Workflow stage for this call")
    response_text: str | None = Field(
        default=None, description="Recorded response string for successful playback"
    )
    error_to_raise: str | None = Field(
        default=None, description="Simulated error message to raise as AdapterError"
    )

    @model_validator(mode="after")
    def validate_exchange_payload(self) -> "RecordedExchange":
        has_response = self.response_text is not None and bool(self.response_text.strip())
        has_error = self.error_to_raise is not None and bool(self.error_to_raise.strip())

        if not (has_response ^ has_error):
            raise ValueError(
                "RecordedExchange requires exactly one of non-empty response_text "
                "or non-empty error_to_raise"
            )

        if self.response_text is not None and CREDENTIAL_PATTERN.search(self.response_text):
            raise ValueError(
                "RecordedExchange response_text contains a likely credential pattern. "
                "Fixtures must contain synthetic, non-sensitive data only."
            )

        if self.error_to_raise is not None and CREDENTIAL_PATTERN.search(self.error_to_raise):
            raise ValueError(
                "RecordedExchange error_to_raise contains a likely credential pattern. "
                "Fixtures must contain synthetic, non-sensitive data only."
            )

        return self


class ReplayFixture(StrictBaseModel):
    """Versioned container holding recorded sequential agent/judge exchanges."""

    schema_version: SupportedSchemaVersion = CURRENT_SCHEMA_VERSION
    fixture_id: str = Field(..., min_length=1, description="Unique fixture identifier")
    description: str = Field(..., min_length=1, description="Summary of the recorded scenario")
    is_synthetic: bool = Field(default=True, description="Enforces synthetic data provenance")
    exchanges: list[RecordedExchange] = Field(
        ..., min_length=1, description="Sequential list of recorded exchanges"
    )

    @model_validator(mode="after")
    def validate_fixture_invariants(self) -> "ReplayFixture":
        if not self.is_synthetic:
            raise ValueError("ReplayFixture must have is_synthetic=True for offline testing")

        indices = [e.call_index for e in self.exchanges]
        expected = list(range(len(self.exchanges)))
        if indices != expected:
            raise ValueError(
                f"Exchange call_index sequence must start at 0 and increment sequentially. "
                f"Expected {expected}, got {indices}"
            )

        return self
