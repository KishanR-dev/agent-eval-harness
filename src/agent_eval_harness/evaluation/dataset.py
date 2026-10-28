"""Dataset loading, validation, and serialization utilities."""

import json
from collections.abc import Sequence
from pathlib import Path

from agent_eval_harness.evaluation.models import EvaluationCase

DEFAULT_DATASET_PATH = Path("datasets") / "synthetic_cases.json"


def load_dataset(dataset_path: str | Path = DEFAULT_DATASET_PATH) -> list[EvaluationCase]:
    """Load and validate synthetic evaluation cases from a JSON file.

    Args:
        dataset_path: Path to the JSON dataset file.

    Returns:
        Validated list of EvaluationCase models.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If JSON is invalid or cases fail contract validation.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset file not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")
    raw_data = json.loads(content)

    if not isinstance(raw_data, list):
        raise ValueError(
            f"Dataset root must be a JSON array of cases, got {type(raw_data).__name__}"
        )

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()

    for idx, raw_case in enumerate(raw_data):
        try:
            case = EvaluationCase.model_validate(raw_case)
        except Exception as exc:
            raise ValueError(f"Dataset validation failed at index {idx}: {exc}") from exc

        if case.case_id in seen_ids:
            raise ValueError(f"Duplicate case_id detected: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)

    return cases


def dump_dataset(cases: Sequence[EvaluationCase], dataset_path: str | Path) -> None:
    """Save evaluation cases to a pretty-printed JSON file."""
    path = Path(dataset_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = [case.model_dump(mode="json") for case in cases]
    path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
