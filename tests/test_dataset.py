"""Unit tests for synthetic dataset loading, schema validation, and serialization."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_eval_harness.evaluation import DEFAULT_DATASET_PATH, dump_dataset, load_dataset
from agent_eval_harness.evaluation.models import EvaluationCase


def test_load_default_dataset_20_cases() -> None:
    """Default synthetic dataset loads successfully and contains exactly 20 valid cases."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    assert len(cases) == 20

    # Assert stable ID format and uniqueness
    case_ids = [c.case_id for c in cases]
    assert len(case_ids) == len(set(case_ids))
    for i, cid in enumerate(case_ids, start=1):
        assert cid == f"CASE-{i:03d}"

    # Assert all cases are strictly synthetic and versioned
    for case in cases:
        assert case.is_synthetic is True
        assert case.dataset_version == "1.0.0"
        assert len(case.name) > 0
        assert len(case.description) > 0
        assert case.lead_input.lead_id.startswith("synth_lead_")


def test_load_dataset_missing_file(tmp_path: Path) -> None:
    """Loading a non-existent file path raises FileNotFoundError."""
    missing = tmp_path / "non_existent.json"
    with pytest.raises(FileNotFoundError):
        load_dataset(missing)


def test_load_dataset_non_list_root(tmp_path: Path) -> None:
    """Loading a JSON dataset with an object root raises ValueError."""
    bad_file = tmp_path / "bad_root.json"
    bad_file.write_text(json.dumps({"error": "not a list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset root must be a JSON array"):
        load_dataset(bad_file)


def test_load_dataset_duplicate_id(tmp_path: Path) -> None:
    """Loading a dataset with duplicate case_id raises ValueError."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    duplicated = [cases[0].model_dump(mode="json"), cases[0].model_dump(mode="json")]
    dup_file = tmp_path / "duplicate.json"
    dup_file.write_text(json.dumps(duplicated), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate case_id detected: CASE-001"):
        load_dataset(dup_file)


def test_load_dataset_invalid_case_schema(tmp_path: Path) -> None:
    """Loading a dataset with malformed case data raises ValueError."""
    bad_file = tmp_path / "invalid_case.json"
    bad_file.write_text(json.dumps([{"case_id": "BAD_ID"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset validation failed at index 0"):
        load_dataset(bad_file)


def test_dump_and_roundtrip_dataset(tmp_path: Path) -> None:
    """Dumping and reloading cases preserves schema fidelity."""
    original_cases = load_dataset(DEFAULT_DATASET_PATH)[:3]
    out_file = tmp_path / "roundtrip.json"
    dump_dataset(original_cases, out_file)

    reloaded = load_dataset(out_file)
    assert len(reloaded) == 3
    assert [c.case_id for c in reloaded] == [c.case_id for c in original_cases]


def test_evaluation_case_synthetic_invariant() -> None:
    """EvaluationCase strictly rejects is_synthetic=False."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    raw = cases[0].model_dump(mode="json")
    raw["is_synthetic"] = False

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(raw)
