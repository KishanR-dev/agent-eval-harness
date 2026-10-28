"""Contract definitions for the inter-agent boundary handoff."""

from enum import StrEnum

from pydantic import Field, field_validator

from agent_eval_harness.contracts.base import StrictBaseModel, ensure_non_empty_string
from agent_eval_harness.contracts.lead import LeadQualificationResult


class OutreachChannel(StrEnum):
    """Supported outreach communication channels."""

    EMAIL = "EMAIL"
    LINKEDIN = "LINKEDIN"


class OutreachTone(StrEnum):
    """Target tone for drafted outreach copy."""

    PROFESSIONAL = "PROFESSIONAL"
    CASUAL = "CASUAL"
    CONSULTATIVE = "CONSULTATIVE"


class OutreachHandoff(StrictBaseModel):
    """Boundary payload passed from Coordinator/Lead Agent to the Outreach Drafter.

    Encapsulates validated lead context and drafting requirements.
    Coordinator-level business policy (e.g. routing disqualified leads)
    is handled by the orchestration runner, preserving schema modularity.
    """

    lead: LeadQualificationResult = Field(
        ...,
        description="Validated upstream lead qualification result.",
    )
    channel: OutreachChannel = Field(
        ...,
        strict=False,
        description="Target communication channel.",
    )
    target_persona: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Job title or persona to address in the outreach message.",
    )
    tone_preference: OutreachTone = Field(
        default=OutreachTone.PROFESSIONAL,
        strict=False,
        description="Target voice and style of the draft.",
    )
    max_words: int = Field(
        default=150,
        ge=10,
        le=500,
        description="Hard upper ceiling on word count for the outreach draft.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Specific instructions or forbidden topics for drafting.",
    )

    @field_validator("target_persona")
    @classmethod
    def validate_target_persona(cls, v: str) -> str:
        return ensure_non_empty_string(v, "target_persona")

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, items: list[str]) -> list[str]:
        for i, item in enumerate(items):
            ensure_non_empty_string(item, f"constraints[{i}]")
        return items
