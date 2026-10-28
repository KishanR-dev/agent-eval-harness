"""Inbound lead data contract for Stage 1 Lead Qualification Agent."""

from pydantic import Field, field_validator

from agent_eval_harness.contracts.base import (
    CURRENT_SCHEMA_VERSION,
    StrictBaseModel,
    SupportedSchemaVersion,
    ensure_non_empty_string,
)


class LeadInput(StrictBaseModel):
    """Minimal typed inbound context for prospect qualification.

    Represents raw inbound lead inquiry context. Contains only descriptive
    fields without business rules or arbitrary threshold policies.
    """

    schema_version: SupportedSchemaVersion = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="SemVer schema version for contract compatibility.",
    )
    lead_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Unique synthetic lead identifier.",
    )
    company_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Fictional company name.",
    )
    industry: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Industry sector.",
    )
    notes: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Inbound inquiry, prospect notes, or background summary.",
    )
    employee_count: int | None = Field(
        default=None,
        ge=1,
        description="Optional employee headcount estimate.",
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        return ensure_non_empty_string(v, "company_name")

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, v: str) -> str:
        return ensure_non_empty_string(v, "industry")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str) -> str:
        return ensure_non_empty_string(v, "notes")
