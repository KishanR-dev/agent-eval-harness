"""Lightweight two-stage workflow coordinator and execution results."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent_eval_harness.agents.base import sanitize_validation_error
from agent_eval_harness.agents.lead_agent import LeadQualificationAgent
from agent_eval_harness.agents.outreach_agent import OutreachDrafterAgent
from agent_eval_harness.contracts.handoff import (
    OutreachChannel,
    OutreachHandoff,
    OutreachTone,
)
from agent_eval_harness.contracts.lead import (
    LeadQualificationResult,
    QualificationStatus,
)
from agent_eval_harness.contracts.lead_input import LeadInput
from agent_eval_harness.contracts.outreach import OutreachDraftResult
from agent_eval_harness.exceptions import AgentExecutionError


class CoordinatorStatus(StrEnum):
    """Explicit lifecycle status for coordinator workflow runs."""

    COMPLETED = "COMPLETED"
    SKIPPED_DISQUALIFIED = "SKIPPED_DISQUALIFIED"
    SKIPPED_NEEDS_REVIEW = "SKIPPED_NEEDS_REVIEW"
    FAILED = "FAILED"


class OutreachConfig(BaseModel):
    """Configuration parameters for downstream outreach drafting."""

    model_config = ConfigDict(extra="forbid", strict=True)

    channel: OutreachChannel = Field(
        default=OutreachChannel.EMAIL,
        strict=False,
        description="Target outreach communication channel.",
    )
    target_persona: str = Field(
        default="Decision Maker",
        min_length=1,
        max_length=100,
        description="Target job persona or title.",
    )
    tone_preference: OutreachTone = Field(
        default=OutreachTone.PROFESSIONAL,
        strict=False,
        description="Desired copy voice and style.",
    )
    max_words: int = Field(
        default=150,
        ge=10,
        le=500,
        description="Maximum words allowed in the generated draft.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Drafting rules, boundaries, and forbidden claims.",
    )


class CoordinatorResult(BaseModel):
    """Structured summary of a workflow coordination execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: CoordinatorStatus
    lead_result: LeadQualificationResult | None = None
    handoff: OutreachHandoff | None = None
    draft_result: OutreachDraftResult | None = None
    failed_stage: (
        Literal["lead_qualification", "handoff_construction", "outreach_drafting"] | None
    ) = None
    error_category: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_state_invariants(self) -> "CoordinatorResult":
        """Enforce strict state consistency invariants across all lifecycle statuses."""
        if self.status == CoordinatorStatus.COMPLETED:
            if self.lead_result is None or self.handoff is None or self.draft_result is None:
                raise ValueError(
                    "COMPLETED status requires populated lead_result, handoff, and draft_result"
                )
            if (
                self.failed_stage is not None
                or self.error_category is not None
                or self.error_message is not None
            ):
                raise ValueError("COMPLETED status must not have failure fields populated")

        elif self.status == CoordinatorStatus.SKIPPED_DISQUALIFIED:
            if (
                self.lead_result is None
                or self.lead_result.qualification_status != QualificationStatus.DISQUALIFIED
            ):
                raise ValueError(
                    "SKIPPED_DISQUALIFIED status requires lead_result with DISQUALIFIED status"
                )
            if self.handoff is not None or self.draft_result is not None:
                raise ValueError(
                    "SKIPPED_DISQUALIFIED status must not have handoff or draft_result"
                )
            if (
                self.failed_stage is not None
                or self.error_category is not None
                or self.error_message is not None
            ):
                raise ValueError(
                    "SKIPPED_DISQUALIFIED status must not have failure fields populated"
                )

        elif self.status == CoordinatorStatus.SKIPPED_NEEDS_REVIEW:
            if (
                self.lead_result is None
                or self.lead_result.qualification_status != QualificationStatus.NEEDS_REVIEW
            ):
                raise ValueError(
                    "SKIPPED_NEEDS_REVIEW status requires lead_result with NEEDS_REVIEW status"
                )
            if self.handoff is not None or self.draft_result is not None:
                raise ValueError(
                    "SKIPPED_NEEDS_REVIEW status must not have handoff or draft_result"
                )
            if (
                self.failed_stage is not None
                or self.error_category is not None
                or self.error_message is not None
            ):
                raise ValueError(
                    "SKIPPED_NEEDS_REVIEW status must not have failure fields populated"
                )

        else:  # CoordinatorStatus.FAILED
            if (
                self.failed_stage is None
                or self.error_category is None
                or self.error_message is None
            ):
                raise ValueError(
                    "FAILED status requires failed_stage, error_category, and error_message"
                )
            if self.draft_result is not None:
                raise ValueError("FAILED status must not have draft_result populated")

        return self


class WorkflowCoordinator:
    """Orchestrates the two-stage pipeline: Lead Qualification -> Outreach Drafting."""

    def __init__(
        self,
        lead_agent: LeadQualificationAgent,
        outreach_agent: OutreachDrafterAgent,
    ) -> None:
        """Initialize coordinator with stage agents.

        Args:
            lead_agent: Configured LeadQualificationAgent.
            outreach_agent: Configured OutreachDrafterAgent.
        """
        self.lead_agent = lead_agent
        self.outreach_agent = outreach_agent

    def run(
        self,
        lead_input: LeadInput,
        outreach_config: OutreachConfig | None = None,
    ) -> CoordinatorResult:
        """Execute the two-stage agent workflow against an inbound lead.

        Args:
            lead_input: Validated inbound prospect context.
            outreach_config: Optional drafting configuration parameters.

        Returns:
            CoordinatorResult detailing lifecycle outcome and stage artifacts.

        Raises:
            Exception: Unexpected programming/runtime errors propagate directly.
        """
        config = outreach_config if outreach_config is not None else OutreachConfig()

        # Stage 1: Lead Qualification
        try:
            lead_result = self.lead_agent.qualify(lead_input)
        except AgentExecutionError as exc:
            return CoordinatorResult(
                status=CoordinatorStatus.FAILED,
                failed_stage="lead_qualification",
                error_category=exc.error_category,
                error_message=exc.message,
            )

        # Routing: Non-qualified leads cleanly skip Stage 2
        if lead_result.qualification_status == QualificationStatus.DISQUALIFIED:
            return CoordinatorResult(
                status=CoordinatorStatus.SKIPPED_DISQUALIFIED,
                lead_result=lead_result,
            )

        if lead_result.qualification_status == QualificationStatus.NEEDS_REVIEW:
            return CoordinatorResult(
                status=CoordinatorStatus.SKIPPED_NEEDS_REVIEW,
                lead_result=lead_result,
            )

        # Stage 1.5: Inter-Agent Boundary Handoff Construction
        try:
            handoff = OutreachHandoff(
                lead=lead_result,
                channel=config.channel,
                target_persona=config.target_persona,
                tone_preference=config.tone_preference,
                max_words=config.max_words,
                constraints=config.constraints,
            )
        except ValidationError as exc:
            return CoordinatorResult(
                status=CoordinatorStatus.FAILED,
                lead_result=lead_result,
                failed_stage="handoff_construction",
                error_category="ContractValidationError",
                error_message=sanitize_validation_error(exc),
            )

        # Stage 2: Outreach Drafting
        try:
            draft_result = self.outreach_agent.draft(handoff)
        except AgentExecutionError as exc:
            return CoordinatorResult(
                status=CoordinatorStatus.FAILED,
                lead_result=lead_result,
                handoff=handoff,
                failed_stage="outreach_drafting",
                error_category=exc.error_category,
                error_message=exc.message,
            )

        return CoordinatorResult(
            status=CoordinatorStatus.COMPLETED,
            lead_result=lead_result,
            handoff=handoff,
            draft_result=draft_result,
        )
