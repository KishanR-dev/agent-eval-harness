"""Base contract definitions and versioning rules.

All inter-agent contracts inherit from StrictBaseModel, which enforces:
1. Strict type checking (strict=True) to disallow implicit type coercion.
2. Rejection of unmodeled or hallucinated extra fields (extra="forbid").
3. Explicit SemVer schema versioning constrained in both type system / JSON Schema
   (via Literal typing) and runtime validation.

Rationale regarding model mutability:
frozen=True is omitted for this contract layer. Pydantic's frozen=True only prevents
top-level attribute re-assignment; it does not provide deep immutability or thread-safety
when models contain mutable collections (such as list[str] in pain points, constraints,
or disclaimers). To avoid misleading claims of thread safety, models maintain strict
structural validation without superficial top-level freezing.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

SupportedSchemaVersion = Literal["1.0.0"]
CURRENT_SCHEMA_VERSION: Final[SupportedSchemaVersion] = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset(["1.0.0"])


class StrictBaseModel(BaseModel):
    """Strictly validated base model for all agent contracts.

    Enforces extra='forbid' and strict=True.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    schema_version: SupportedSchemaVersion = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="SemVer schema version for contract compatibility.",
    )


def ensure_non_empty_string(value: str, field_name: str) -> str:
    """Validate that a string is neither empty nor solely whitespace."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty or contain only whitespace")
    return value
