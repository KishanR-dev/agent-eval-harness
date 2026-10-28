"""Tests for bounded static secret scanner (scripts/scan_secrets.py).

Validates detection rules, false-positive resistance, log redaction, and CLI behavior.
Note: Planted test credentials are built dynamically in memory to prevent the scanner
from detecting this test file as a leak.
"""

from pathlib import Path

import pytest

from scripts.scan_secrets import (
    ScanFinding,
    main,
    scan_directory,
    scan_file,
)


def _build_test_token(prefix: str, filler: str, length: int) -> str:
    """Build synthetic test tokens dynamically to prevent static scanning of this file."""
    return f"{prefix}{filler * length}"


@pytest.fixture
def synthetic_secret_samples() -> dict[str, str]:
    """Dynamically generated test patterns corresponding to scanner rules."""
    return {
        "OPENAI_API_KEY": _build_test_token("s" + "k-", "A", 25),
        "GOOGLE_API_KEY": _build_test_token("AI" + "za", "B", 35),
        "GITHUB_PAT": _build_test_token("gh" + "p_", "C", 36),
        "PRIVATE_KEY": "-----" + "BEGIN RSA PRIVATE KEY-----",
        "BEARER_TOKEN": f"Be{'arer'} " + ("D" * 30),
    }


def test_scanner_detects_all_defined_rules(
    tmp_path: Path, synthetic_secret_samples: dict[str, str]
) -> None:
    """Every defined rule must detect its corresponding synthetic secret pattern."""
    for rule_name, token in synthetic_secret_samples.items():
        test_file = tmp_path / f"test_{rule_name.lower()}.txt"
        test_file.write_text(f"dummy_config = '{token}'\n", encoding="utf-8")

        findings = scan_file(test_file)
        assert len(findings) == 1, f"Expected 1 finding for rule {rule_name}"
        assert findings[0].rule_name == rule_name
        assert findings[0].line_number == 1
        assert findings[0].file_path == test_file


def test_scanner_redacts_matched_secret_in_log(
    tmp_path: Path, synthetic_secret_samples: dict[str, str]
) -> None:
    """Formatted log output must strictly redact and never expose matched secret tokens."""
    for rule_name, token in synthetic_secret_samples.items():
        finding = ScanFinding(
            file_path=tmp_path / "sensitive.env",
            line_number=42,
            rule_name=rule_name,
        )
        log_output = finding.format_log(base_dir=tmp_path)

        # Output must include rule and location
        assert "sensitive.env:42" in log_output
        assert rule_name in log_output
        assert "[CONTENT REDACTED]" in log_output

        # Output must NEVER contain the secret value
        assert token not in log_output


def test_scanner_clean_on_legitimate_synthetic_fixtures(tmp_path: Path) -> None:
    """Legitimate synthetic placeholders, IDs, and tokens must not trigger false positives."""
    clean_content = (
        "lead_id = 'synth_lead_001'\n"
        "secret_flag = 'SYNTH_SECRET_TOKEN_9912'\n"
        "key_alpha = 'SYNTH_KEY_ALPHA_7731'\n"
        "injection_token = 'INJECTION_FLAG_PWNED_99'\n"
        "api_key_placeholder = 'sk-placeholder-not-enough-chars'\n"
        "status = 'QUALIFIED'\n"
    )
    clean_file = tmp_path / "clean_data.py"
    clean_file.write_text(clean_content, encoding="utf-8")

    findings = scan_file(clean_file)
    assert len(findings) == 0, f"False positive detected: {findings}"


def test_scanner_skips_excluded_directories_and_extensions(tmp_path: Path) -> None:
    """Excluded directories (.venv, __pycache__) and extensions (.zip, .pyc) are ignored."""
    # 1. Ignored directory
    venv_dir = tmp_path / ".venv" / "sub"
    venv_dir.mkdir(parents=True)
    venv_file = venv_dir / "secret.py"
    venv_file.write_text(f"k = '{_build_test_token('s' + 'k-', 'X', 25)}'\n", encoding="utf-8")

    # 2. Ignored extension
    zip_file = tmp_path / "archive.zip"
    zip_file.write_text(f"k = '{_build_test_token('s' + 'k-', 'Y', 25)}'\n", encoding="utf-8")

    count, findings = scan_directory(target_dir=tmp_path, explicit_targets=[".venv", "archive.zip"])
    assert count == 0
    assert len(findings) == 0


def test_scanner_main_cli_success_and_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI returns 0 on clean scan and 1 on detected secrets, redacting stdout/stderr."""
    # 1. Clean run on empty tmp_path
    exit_code_clean = main([str(tmp_path), "--targets"])
    captured_clean = capsys.readouterr()
    assert exit_code_clean == 0
    assert "[SECURITY SCAN PASSED]" in captured_clean.out

    # 2. Leaked secret in tmp_path
    secret_val = _build_test_token("s" + "k-", "Z", 25)
    dirty_file = tmp_path / "dirty.txt"
    dirty_file.write_text(f"api_key={secret_val}\n", encoding="utf-8")

    exit_code_dirty = main([str(tmp_path), "--targets", "dirty.txt"])
    captured_dirty = capsys.readouterr()
    assert exit_code_dirty == 1
    assert "[SECURITY SCAN FAILED]" in captured_dirty.err
    assert "OPENAI_API_KEY" in captured_dirty.err
    assert "[CONTENT REDACTED]" in captured_dirty.err
    # Crucial: The actual secret string must NEVER appear in stderr
    assert secret_val not in captured_dirty.err
    assert secret_val not in captured_dirty.out


def test_scanner_main_cli_invalid_root(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI returns 2 when target root is not an existing directory."""
    exit_code = main(["/nonexistent/directory/path/here"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Target root is not a directory" in captured.err


def test_scan_real_project_files_clean() -> None:
    """Verifies that the actual repository contains zero secret pattern detections."""
    repo_root = Path(__file__).resolve().parent.parent
    files_count, findings = scan_directory(target_dir=repo_root)

    assert files_count >= 40, f"Expected to scan at least 40 files, scanned {files_count}"
    assert findings == [], f"Unexpected secret findings in repository: {findings}"
