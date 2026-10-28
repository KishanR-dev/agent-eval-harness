"""Comprehensive unit tests for inter-agent Pydantic v2 contracts.

Tests cover:
- Valid payload parsing for all contracts
- Schema versioning: omitted, supported, unsupported for all three contracts
- Nested model validation and error propagation in OutreachHandoff
- Strictness: extra="forbid" and strict=True (no silent type coercion)
- Rejection of empty and whitespace-only strings
- Immutability enforcement (frozen=True)
- Canonical qualification status and separation from business-policy checks
- Channel structural consistency rules (EMAIL vs LINKEDIN)
- Derived word_count property and exclusion from raw payload
- JSON Schema generation inspection without assuming $defs exists everywhere
"""

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from agent_eval_harness.contracts import (
    CURRENT_SCHEMA_VERSION,
    LeadInput,
    LeadQualificationResult,
    OutreachChannel,
    OutreachDraftResult,
    OutreachHandoff,
    OutreachTone,
    QualificationStatus,
    export_json_schemas,
)

# ============================================================================
# 1. Happy path & Canonical Qualification Tests (D-016, Item 1)
# ============================================================================


def test_valid_lead_qualification_result(valid_lead_payload: dict[str, Any]) -> None:
    """A fully populated valid payload instantiates LeadQualificationResult."""
    result = LeadQualificationResult.model_validate(valid_lead_payload)
    assert result.lead_id == "lead_synth_101"
    assert result.company_name == "Synthetix Dynamics Ltd"
    assert result.qualification_status == QualificationStatus.QUALIFIED
    assert result.is_qualified is True
    assert result.fit_score == 85
    assert len(result.key_pain_points) == 2
    assert result.recommended_angle is not None


@pytest.mark.parametrize(
    "status,expected_is_qualified",
    [
        (QualificationStatus.QUALIFIED, True),
        (QualificationStatus.DISQUALIFIED, False),
        (QualificationStatus.NEEDS_REVIEW, False),
    ],
)
def test_canonical_qualification_status(
    valid_lead_payload: dict[str, Any],
    status: QualificationStatus,
    expected_is_qualified: bool,
) -> None:
    """Verify qualification_status is the canonical source of truth (D-016)."""
    payload = copy.deepcopy(valid_lead_payload)
    payload["qualification_status"] = status.value
    result = LeadQualificationResult.model_validate(payload)
    assert result.qualification_status == status
    assert result.is_qualified is expected_is_qualified


def test_structural_validation_avoids_arbitrary_business_rules(
    valid_lead_payload: dict[str, Any],
) -> None:
    """Per D-015 and D-016, structural contracts do not impose arbitrary thresholds.

    A low fit score with QUALIFIED or a high score with DISQUALIFIED is structurally
    valid at the contract layer; evaluation of alignment belongs to evaluation checks.
    """
    # Low score with QUALIFIED
    low_score_payload = copy.deepcopy(valid_lead_payload)
    low_score_payload["fit_score"] = 5
    low_score_payload["qualification_status"] = "QUALIFIED"
    res_low = LeadQualificationResult.model_validate(low_score_payload)
    assert res_low.fit_score == 5
    assert res_low.qualification_status == QualificationStatus.QUALIFIED

    # High score with DISQUALIFIED
    high_score_payload = copy.deepcopy(valid_lead_payload)
    high_score_payload["fit_score"] = 98
    high_score_payload["qualification_status"] = "DISQUALIFIED"
    res_high = LeadQualificationResult.model_validate(high_score_payload)
    assert res_high.fit_score == 98
    assert res_high.qualification_status == QualificationStatus.DISQUALIFIED


def test_valid_outreach_handoff(valid_handoff_payload: dict[str, Any]) -> None:
    """A valid handoff payload parses correctly with nested LeadQualificationResult."""
    handoff = OutreachHandoff.model_validate(valid_handoff_payload)
    assert handoff.channel == OutreachChannel.EMAIL
    assert handoff.target_persona == "VP of Infrastructure Engineering"
    assert handoff.tone_preference == OutreachTone.CONSULTATIVE
    assert handoff.max_words == 120
    assert handoff.lead.lead_id == "lead_synth_101"
    assert len(handoff.constraints) == 2


def test_valid_email_draft_result(valid_email_draft_payload: dict[str, Any]) -> None:
    """A valid email draft parses with subject line and derived word count."""
    draft = OutreachDraftResult.model_validate(valid_email_draft_payload)
    assert draft.channel == OutreachChannel.EMAIL
    assert draft.subject_line is not None
    assert "compliance" in draft.subject_line
    assert draft.word_count == len(draft.body.split())
    assert draft.word_count > 0


def test_valid_linkedin_draft_result(
    valid_linkedin_draft_payload: dict[str, Any],
) -> None:
    """A valid LinkedIn draft parses with None subject line."""
    draft = OutreachDraftResult.model_validate(valid_linkedin_draft_payload)
    assert draft.channel == OutreachChannel.LINKEDIN
    assert draft.subject_line is None
    assert draft.word_count == len(draft.body.split())


# ============================================================================
# 2. Schema Versioning Tests (Omitted, Supported, Unsupported)
# ============================================================================


@pytest.mark.parametrize(
    "model_cls,base_fixture_name",
    [
        (LeadQualificationResult, "valid_lead_payload"),
        (OutreachHandoff, "valid_handoff_payload"),
        (OutreachDraftResult, "valid_email_draft_payload"),
    ],
)
def test_schema_version_omitted_defaults_to_current(
    model_cls: type[Any],
    base_fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """When schema_version is omitted, contract defaults to CURRENT_SCHEMA_VERSION."""
    payload = copy.deepcopy(request.getfixturevalue(base_fixture_name))
    del payload["schema_version"]
    instance = model_cls.model_validate(payload)
    assert instance.schema_version == CURRENT_SCHEMA_VERSION


@pytest.mark.parametrize(
    "model_cls,base_fixture_name",
    [
        (LeadQualificationResult, "valid_lead_payload"),
        (OutreachHandoff, "valid_handoff_payload"),
        (OutreachDraftResult, "valid_email_draft_payload"),
    ],
)
def test_schema_version_supported_explicit(
    model_cls: type[Any],
    base_fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Explicit supported schema_version ('1.0.0') is accepted."""
    payload = copy.deepcopy(request.getfixturevalue(base_fixture_name))
    payload["schema_version"] = "1.0.0"
    instance = model_cls.model_validate(payload)
    assert instance.schema_version == "1.0.0"


@pytest.mark.parametrize(
    "unsupported_version",
    ["0.9.0", "2.0.0", "1.0.1", "v1.0.0", "dev", ""],
)
@pytest.mark.parametrize(
    "model_cls,base_fixture_name",
    [
        (LeadQualificationResult, "valid_lead_payload"),
        (OutreachHandoff, "valid_handoff_payload"),
        (OutreachDraftResult, "valid_email_draft_payload"),
    ],
)
def test_schema_version_unsupported_rejected(
    model_cls: type[Any],
    base_fixture_name: str,
    unsupported_version: str,
    request: pytest.FixtureRequest,
) -> None:
    """Unsupported explicit schema_version values are rejected with clear error."""
    payload = copy.deepcopy(request.getfixturevalue(base_fixture_name))
    payload["schema_version"] = unsupported_version
    with pytest.raises(ValidationError) as exc_info:
        model_cls.model_validate(payload)
    errors = exc_info.value.errors()
    assert any("schema_version" in str(err["loc"]) for err in errors)
    assert any(err["type"] == "literal_error" for err in errors)
    assert any("1.0.0" in err["msg"] for err in errors)


# ============================================================================
# 3. Nested Validation in OutreachHandoff
# ============================================================================


def test_handoff_rejects_invalid_nested_lead(
    valid_handoff_payload: dict[str, Any],
) -> None:
    """OutreachHandoff validation fails if the nested lead payload is invalid."""
    payload = copy.deepcopy(valid_handoff_payload)
    # Remove mandatory lead_id from nested lead
    del payload["lead"]["lead_id"]

    with pytest.raises(ValidationError) as exc_info:
        OutreachHandoff.model_validate(payload)
    assert any("lead" in str(err["loc"]) for err in exc_info.value.errors())


def test_handoff_rejects_unsupported_nested_lead_schema_version(
    valid_handoff_payload: dict[str, Any],
) -> None:
    """OutreachHandoff rejects nested lead with an unsupported schema_version."""
    payload = copy.deepcopy(valid_handoff_payload)
    payload["lead"]["schema_version"] = "99.0.0"

    with pytest.raises(ValidationError) as exc_info:
        OutreachHandoff.model_validate(payload)
    errors = exc_info.value.errors()
    assert any("lead" in str(err["loc"]) and "schema_version" in str(err["loc"]) for err in errors)
    assert any(err["type"] == "literal_error" for err in errors)


def test_handoff_rejects_extra_fields_in_nested_lead(
    valid_handoff_payload: dict[str, Any],
) -> None:
    """OutreachHandoff rejects extra forbidden fields in the nested lead object."""
    payload = copy.deepcopy(valid_handoff_payload)
    payload["lead"]["unauthorized_meta"] = "leak"

    with pytest.raises(ValidationError) as exc_info:
        OutreachHandoff.model_validate(payload)
    errors = exc_info.value.errors()
    assert any("unauthorized_meta" in str(err["loc"]) for err in errors)


# ============================================================================
# 4. Strictness (extra="forbid" & strict=True)
# ============================================================================


@pytest.mark.parametrize(
    "model_cls,base_fixture_name",
    [
        (LeadQualificationResult, "valid_lead_payload"),
        (OutreachHandoff, "valid_handoff_payload"),
        (OutreachDraftResult, "valid_email_draft_payload"),
    ],
)
def test_extra_fields_forbidden(
    model_cls: type[Any],
    base_fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Unexpected fields in payload are strictly rejected per extra='forbid'."""
    payload = copy.deepcopy(request.getfixturevalue(base_fixture_name))
    payload["unexpected_injected_field"] = "hallucinated_data"
    with pytest.raises(ValidationError) as exc_info:
        model_cls.model_validate(payload)
    errors = exc_info.value.errors()
    assert any(err["type"] == "extra_forbidden" for err in errors)


def test_strict_type_checking_no_coercion(valid_lead_payload: dict[str, Any]) -> None:
    """String is not coerced to int under strict=True."""
    payload = copy.deepcopy(valid_lead_payload)
    payload["fit_score"] = "85"  # String instead of int
    with pytest.raises(ValidationError) as exc_info:
        LeadQualificationResult.model_validate(payload)
    errors = exc_info.value.errors()
    assert any("int_type" in err["type"] or "int_parsing" in err["type"] for err in errors)


def test_strict_type_checking_no_int_to_str_coercion(
    valid_lead_payload: dict[str, Any],
) -> None:
    """Integer is not coerced to string under strict=True."""
    payload = copy.deepcopy(valid_lead_payload)
    payload["company_name"] = 12345
    with pytest.raises(ValidationError) as exc_info:
        LeadQualificationResult.model_validate(payload)
    errors = exc_info.value.errors()
    assert any("string_type" in err["type"] for err in errors)


# ============================================================================
# 5. Rejection of Empty and Whitespace-Only Strings
# ============================================================================


@pytest.mark.parametrize("empty_val", ["", "   ", "\t\n  "])
def test_lead_rejects_empty_or_whitespace_strings(
    valid_lead_payload: dict[str, Any],
    empty_val: str,
) -> None:
    """Lead contract explicitly rejects empty or whitespace-only string values."""
    # Company name
    p1 = copy.deepcopy(valid_lead_payload)
    p1["company_name"] = empty_val
    with pytest.raises(ValidationError):
        LeadQualificationResult.model_validate(p1)

    # Industry
    p2 = copy.deepcopy(valid_lead_payload)
    p2["industry"] = empty_val
    with pytest.raises(ValidationError):
        LeadQualificationResult.model_validate(p2)

    # Summary
    p3 = copy.deepcopy(valid_lead_payload)
    p3["summary"] = empty_val
    with pytest.raises(ValidationError):
        LeadQualificationResult.model_validate(p3)

    # Pain points item
    p4 = copy.deepcopy(valid_lead_payload)
    p4["key_pain_points"] = ["Valid point", empty_val]
    with pytest.raises(ValidationError):
        LeadQualificationResult.model_validate(p4)

    # Recommended angle whitespace
    p5 = copy.deepcopy(valid_lead_payload)
    p5["recommended_angle"] = empty_val
    with pytest.raises(ValidationError):
        LeadQualificationResult.model_validate(p5)


def test_lead_accepts_none_recommended_angle(valid_lead_payload: dict[str, Any]) -> None:
    """Lead contract allows recommended_angle to be None."""
    payload = copy.deepcopy(valid_lead_payload)
    payload["recommended_angle"] = None
    result = LeadQualificationResult.model_validate(payload)
    assert result.recommended_angle is None


@pytest.mark.parametrize("empty_val", ["", "   "])
def test_handoff_rejects_empty_target_persona(
    valid_handoff_payload: dict[str, Any],
    empty_val: str,
) -> None:
    """OutreachHandoff rejects empty or whitespace-only target persona."""
    payload = copy.deepcopy(valid_handoff_payload)
    payload["target_persona"] = empty_val
    with pytest.raises(ValidationError):
        OutreachHandoff.model_validate(payload)


@pytest.mark.parametrize("empty_val", ["", "   "])
def test_draft_rejects_empty_body_or_cta(
    valid_email_draft_payload: dict[str, Any],
    empty_val: str,
) -> None:
    """OutreachDraftResult rejects empty or whitespace-only body and call_to_action."""
    p_body = copy.deepcopy(valid_email_draft_payload)
    p_body["body"] = empty_val
    with pytest.raises(ValidationError):
        OutreachDraftResult.model_validate(p_body)

    p_cta = copy.deepcopy(valid_email_draft_payload)
    p_cta["call_to_action"] = empty_val
    with pytest.raises(ValidationError):
        OutreachDraftResult.model_validate(p_cta)


# ============================================================================
# 6. Model Mutability and Rejection of Dynamic Unmodeled Attributes
# ============================================================================


def test_contracts_forbid_dynamic_unmodeled_attributes(
    valid_lead_result: LeadQualificationResult,
    valid_handoff_result: OutreachHandoff,
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """Extra attributes cannot be dynamically attached to contract instances.

    Rationale: frozen=True was omitted because top-level freezing does not provide
    deep immutability or thread-safety for nested mutable collections (e.g. list[str]).
    However, extra='forbid' continues to prevent unmodeled attribute attachment.
    """
    with pytest.raises(ValueError):
        valid_lead_result.unmodeled_attribute = "leak"  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        valid_handoff_result.extra_field = 123  # type: ignore[attr-defined]

    draft = OutreachDraftResult.model_validate(valid_email_draft_payload)
    with pytest.raises(ValueError):
        draft.dynamically_injected_secret = "leak"  # type: ignore[attr-defined]


# ============================================================================
# 7. Channel Structural Rules & Derived Fields (D-015)
# ============================================================================


def test_email_requires_subject_line(valid_email_draft_payload: dict[str, Any]) -> None:
    """Email drafts must include a non-empty subject line."""
    payload = copy.deepcopy(valid_email_draft_payload)
    payload["subject_line"] = None
    with pytest.raises(ValidationError) as exc_info:
        OutreachDraftResult.model_validate(payload)
    assert any(
        "subject_line is required for EMAIL channel" in str(err) for err in exc_info.value.errors()
    )


def test_linkedin_forbids_subject_line(valid_linkedin_draft_payload: dict[str, Any]) -> None:
    """LinkedIn drafts must have subject_line set to None."""
    payload = copy.deepcopy(valid_linkedin_draft_payload)
    payload["subject_line"] = "Unexpected subject for LinkedIn message"
    with pytest.raises(ValidationError) as exc_info:
        OutreachDraftResult.model_validate(payload)
    assert any(
        "subject_line must be None for LINKEDIN channel" in str(err)
        for err in exc_info.value.errors()
    )


def test_word_count_derived_and_not_in_payload(
    valid_email_draft_payload: dict[str, Any],
) -> None:
    """word_count is a derived property (D-015) and rejected if passed in payload."""
    draft = OutreachDraftResult.model_validate(valid_email_draft_payload)
    expected_words = len(valid_email_draft_payload["body"].split())
    assert draft.word_count == expected_words

    # Explicitly including word_count in the payload is rejected by extra="forbid"
    payload_with_extra = copy.deepcopy(valid_email_draft_payload)
    payload_with_extra["word_count"] = expected_words
    with pytest.raises(ValidationError) as exc_info:
        OutreachDraftResult.model_validate(payload_with_extra)
    assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())


# ============================================================================
# 8. JSON Schema Export & Inspection (without assuming $defs everywhere)
# ============================================================================


@pytest.mark.parametrize(
    "contract_name",
    ["LeadInput", "LeadQualificationResult", "OutreachHandoff", "OutreachDraftResult"],
)
def test_json_schema_version_constraint_represented(contract_name: str) -> None:
    """Confirm supported schema versions are constrained in JSON Schema definition."""
    schemas = export_json_schemas()
    assert contract_name in schemas
    schema = schemas[contract_name]

    # Verify top-level object structure and rejection of unmodeled properties
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False
    assert "properties" in schema
    assert "schema_version" in schema["properties"]

    # Verify that the schema version constraint is explicitly embedded in the JSON Schema
    ver_prop = schema["properties"]["schema_version"]
    assert ver_prop.get("type") == "string"
    assert ver_prop.get("default") == CURRENT_SCHEMA_VERSION
    # In standard JSON Schema (Draft 2020-12/OpenAPI), Pydantic emits 'const' for single Literal
    # or 'enum' if multiple versions are allowed
    assert ver_prop.get("const") == CURRENT_SCHEMA_VERSION or ver_prop.get("enum") == [
        CURRENT_SCHEMA_VERSION
    ]


def test_export_json_schemas_structure() -> None:
    """Verify JSON Schema export without making assumptions about $defs location."""
    schemas = export_json_schemas()
    assert set(schemas.keys()) == {
        "LeadInput",
        "LeadQualificationResult",
        "OutreachHandoff",
        "OutreachDraftResult",
    }

    # Inspect LeadQualificationResult schema
    lead_schema = schemas["LeadQualificationResult"]
    assert lead_schema.get("type") == "object"
    assert "properties" in lead_schema
    assert "lead_id" in lead_schema["properties"]
    assert "qualification_status" in lead_schema["properties"]
    assert "schema_version" in lead_schema["properties"]
    assert "required" in lead_schema
    assert "lead_id" in lead_schema["required"]
    assert "qualification_status" in lead_schema["required"]

    # Inspect OutreachDraftResult schema
    draft_schema = schemas["OutreachDraftResult"]
    assert draft_schema.get("type") == "object"
    assert "properties" in draft_schema
    assert "body" in draft_schema["properties"]
    assert "channel" in draft_schema["properties"]
    assert "subject_line" in draft_schema["properties"]
    assert "call_to_action" in draft_schema["properties"]

    # Inspect OutreachHandoff schema (nested model) without assuming fixed $defs layout
    handoff_schema = schemas["OutreachHandoff"]
    assert handoff_schema.get("type") == "object"
    assert "properties" in handoff_schema
    assert "lead" in handoff_schema["properties"]
    assert "channel" in handoff_schema["properties"]

    lead_prop = handoff_schema["properties"]["lead"]
    if "$ref" in lead_prop:
        # Dynamically follow URI reference without assuming key name or path depth
        ref_path = lead_prop["$ref"].lstrip("#/").split("/")
        target: Any = handoff_schema
        for segment in ref_path:
            assert segment in target, f"Reference segment '{segment}' not in schema"
            target = target[segment]
        assert "lead_id" in target.get("properties", {})
    else:
        # Inlined definition
        assert "properties" in lead_prop
        assert "lead_id" in lead_prop["properties"]


# ============================================================================
# 8. LeadInput Contract Tests (Item 2)
# ============================================================================


def test_valid_lead_input(valid_lead_input_payload: dict[str, Any]) -> None:
    """LeadInput parses valid payload successfully."""
    input_model = LeadInput.model_validate(valid_lead_input_payload)
    assert input_model.lead_id == "lead_synth_101"
    assert input_model.company_name == "Synthetix Dynamics Ltd"
    assert input_model.schema_version == CURRENT_SCHEMA_VERSION


def test_lead_input_versioning(valid_lead_input_payload: dict[str, Any]) -> None:
    """LeadInput defaults omitted version, accepts 1.0.0, and rejects unsupported versions."""
    p_omitted = copy.deepcopy(valid_lead_input_payload)
    del p_omitted["schema_version"]
    m_omitted = LeadInput.model_validate(p_omitted)
    assert m_omitted.schema_version == CURRENT_SCHEMA_VERSION

    p_valid = copy.deepcopy(valid_lead_input_payload)
    p_valid["schema_version"] = "1.0.0"
    m_valid = LeadInput.model_validate(p_valid)
    assert m_valid.schema_version == "1.0.0"

    p_unsupported = copy.deepcopy(valid_lead_input_payload)
    p_unsupported["schema_version"] = "2.0.0"
    with pytest.raises(ValidationError):
        LeadInput.model_validate(p_unsupported)


def test_lead_input_extra_forbidden(valid_lead_input_payload: dict[str, Any]) -> None:
    """LeadInput rejects unexpected fields."""
    p = copy.deepcopy(valid_lead_input_payload)
    p["unexpected_field"] = "bad"
    with pytest.raises(ValidationError):
        LeadInput.model_validate(p)


def test_lead_input_whitespace_rejection(valid_lead_input_payload: dict[str, Any]) -> None:
    """LeadInput rejects whitespace-only string fields."""
    for field in ("company_name", "industry", "notes"):
        p = copy.deepcopy(valid_lead_input_payload)
        p[field] = "   "
        with pytest.raises(ValidationError):
            LeadInput.model_validate(p)
