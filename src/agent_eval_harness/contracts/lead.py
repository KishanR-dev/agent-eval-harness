"""Contract definitions for Stage 1 Lead Qualification Agent output."""

from enum import StrEnum

from pydantic import Field, field_validator

from agent_eval_harness.contracts.base import StrictBaseModel, ensure_non_empty_string


class QualificationStatus(StrEnum):
    """Canonical classification for lead qualification status (per D-016)."""

    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class LeadQualificationResult(StrictBaseModel):
    """Structured qualification assessment output produced by the Lead Agent.

    Enforces structural schema constraints, canonical qualification status, and bounds.
    Business-policy evaluations (e.g. alignment between fit score and classification)
    are intentionally deferred to the evaluation runner layer per D-015 and D-016.
    """

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
    qualification_status: QualificationStatus = Field(
        ...,
        strict=False,
        description="Single canonical qualification classification (per D-016).",
    )
    fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Evaluated lead fit score between 0 and 100 inclusive.",
    )
    summary: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Summary rationale for the qualification assessment.",
    )
    key_pain_points: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Identified pain points or business challenges.",
    )
    recommended_angle: str | None = Field(
        default=None,
        max_length=200,
        description="Recommended messaging hook or angle for downstream outreach.",
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        return ensure_non_empty_string(v, "company_name")

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, v: str) -> str:
        return ensure_non_empty_string(v, "industry")

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        return ensure_non_empty_string(v, "summary")

    @field_validator("key_pain_points")
    @classmethod
    def validate_pain_points(cls, items: list[str]) -> list[str]:
        for i, item in enumerate(items):
            ensure_non_empty_string(item, f"key_pain_points[{i}]")
        return items

    @field_validator("recommended_angle")
    @classmethod
    def validate_recommended_angle(cls, v: str | None) -> str | None:
        if v is not None:
            return ensure_non_empty_string(v, "recommended_angle")
        return v

    @property
    def is_qualified(self) -> bool:
        """Convenience property; qualification_status is the canonical source of truth."""
        return self.qualification_status == QualificationStatus.QUALIFIED
