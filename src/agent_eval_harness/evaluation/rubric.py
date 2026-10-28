"""Rubric definitions, dimensions, and anchored scoring criteria."""

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["RubricDimension", "DimensionCriteria", "EvaluationRubric", "DEFAULT_RUBRIC"]


class RubricDimension(StrEnum):
    """Canonical semantic evaluation dimensions for lead qualification and outreach drafting."""

    RELEVANCE_POSITIONING = "relevance_positioning"
    FACTUAL_GROUNDING = "factual_grounding"
    INSTRUCTION_ADHERENCE = "instruction_adherence"


@dataclass(frozen=True)
class DimensionCriteria:
    """Anchored descriptions for scores 1 through 4 for a single rubric dimension."""

    dimension: RubricDimension
    name: str
    description: str
    anchor_1: str
    anchor_2: str
    anchor_3: str
    anchor_4: str


@dataclass(frozen=True)
class EvaluationRubric:
    """Complete evaluation rubric containing criteria for all canonical dimensions."""

    version: str
    criteria: dict[RubricDimension, DimensionCriteria]

    def format_for_prompt(self) -> str:
        """Format rubric into clean structured text for evaluator prompt injection."""
        sections: list[str] = [f"=== SCORING RUBRIC (VERSION {self.version}) ==="]
        sections.append(
            "Evaluate the draft and lead qualification outputs on each of the following "
            "three dimensions on a discrete 1 to 4 ordinal scale.\n"
        )

        for dim in RubricDimension:
            crit = self.criteria[dim]
            sections.append(f"Dimension: {crit.name} (Key: '{crit.dimension.value}')")
            sections.append(f"Description: {crit.description}")
            sections.append("Scoring Anchors:")
            sections.append(f"  [1] {crit.anchor_1}")
            sections.append(f"  [2] {crit.anchor_2}")
            sections.append(f"  [3] {crit.anchor_3}")
            sections.append(f"  [4] {crit.anchor_4}\n")

        return "\n".join(sections)


DEFAULT_RUBRIC = EvaluationRubric(
    version="1.0.0",
    criteria={
        RubricDimension.RELEVANCE_POSITIONING: DimensionCriteria(
            dimension=RubricDimension.RELEVANCE_POSITIONING,
            name="Relevance & Persona Positioning",
            description=(
                "Evaluates whether the qualification summary and outreach draft tailor value "
                "propositions to the prospect's role, company size, and stated technical pains."
            ),
            anchor_1="Generic boilerplate ignoring prospect scale, industry, and challenges.",
            anchor_2="Superficial personalization; mentions company once with generic pitch.",
            anchor_3="Targeted positioning directly addressing persona and specific pains.",
            anchor_4="Exemplary tailoring framing value precisely around architecture and role.",
        ),
        RubricDimension.FACTUAL_GROUNDING: DimensionCriteria(
            dimension=RubricDimension.FACTUAL_GROUNDING,
            name="Factual Grounding & Hallucination Resistance",
            description=(
                "Evaluates whether all claims, numbers, and capabilities are derived strictly from "
                "the supplied prospect context and workflow configuration."
            ),
            anchor_1="Fabricated facts, invented metrics, unverified claims, or fake integrations.",
            anchor_2="Unsupported extrapolation; makes speculative claims not in the input.",
            anchor_3="Grounded in supplied context; claims are directly supported or inferred.",
            anchor_4="Strictly faithful; zero extrapolation and flawless fidelity to context.",
        ),
        RubricDimension.INSTRUCTION_ADHERENCE: DimensionCriteria(
            dimension=RubricDimension.INSTRUCTION_ADHERENCE,
            name="Instruction & Constraint Adherence",
            description=(
                "Evaluates compliance with qualitative tone preferences, negative constraints, "
                "and channel etiquette beyond simple regex checks."
            ),
            anchor_1="Flagrant violation of negative constraints or inappropriate tone.",
            anchor_2="Partially compliant; adheres to tone but violates a negative constraint.",
            anchor_3="Fully compliant with tone, constraints, and professional etiquette.",
            anchor_4="Exemplary execution of tone and constraints with natural CTA and etiquette.",
        ),
    },
)
