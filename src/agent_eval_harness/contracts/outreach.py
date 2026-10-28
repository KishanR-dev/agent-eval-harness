"""Contract definitions for Stage 2 Outreach Drafting Agent output."""

from pydantic import Field, field_validator, model_validator

from agent_eval_harness.contracts.base import StrictBaseModel, ensure_non_empty_string
from agent_eval_harness.contracts.handoff import OutreachChannel


class OutreachDraftResult(StrictBaseModel):
    """Structured outreach message output produced by the Outreach Agent.

    Enforces length limits, channel-specific structural requirements, and
    rejection of unmodeled fields. Word count is derived on-demand via a property
    per D-015 rather than duplicating it as an LLM payload requirement.
    """

    lead_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Lead identifier this draft was generated for.",
    )
    channel: OutreachChannel = Field(
        ...,
        strict=False,
        description="Channel format of the draft.",
    )
    subject_line: str | None = Field(
        default=None,
        max_length=150,
        description="Subject line for email outreach. Must be None for LinkedIn.",
    )
    body: str = Field(
        ...,
        min_length=10,
        max_length=3000,
        description="Draft message content.",
    )
    call_to_action: str = Field(
        ...,
        min_length=5,
        max_length=250,
        description="Specific closing ask or call to action.",
    )
    disclaimers_included: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Regulatory or opt-out notices included in the draft.",
    )

    @field_validator("body")
    @classmethod
    def validate_body(cls, v: str) -> str:
        return ensure_non_empty_string(v, "body")

    @field_validator("call_to_action")
    @classmethod
    def validate_call_to_action(cls, v: str) -> str:
        return ensure_non_empty_string(v, "call_to_action")

    @field_validator("subject_line")
    @classmethod
    def validate_subject_line(cls, v: str | None) -> str | None:
        if v is not None:
            return ensure_non_empty_string(v, "subject_line")
        return v

    @field_validator("disclaimers_included")
    @classmethod
    def validate_disclaimers(cls, items: list[str]) -> list[str]:
        for i, item in enumerate(items):
            ensure_non_empty_string(item, f"disclaimers_included[{i}]")
        return items

    @model_validator(mode="after")
    def validate_channel_structure(self) -> "OutreachDraftResult":
        """Enforce channel-specific structural rules."""
        if self.channel == OutreachChannel.EMAIL:
            if not self.subject_line:
                raise ValueError("subject_line is required for EMAIL channel")
        elif self.channel == OutreachChannel.LINKEDIN and self.subject_line is not None:
            raise ValueError("subject_line must be None for LINKEDIN channel")
        return self

    @property
    def word_count(self) -> int:
        """Derive word count dynamically from the message body per D-015."""
        return len(self.body.split())
