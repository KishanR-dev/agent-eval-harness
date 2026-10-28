"""Lightweight static secret scanner for agent-eval-harness.

Scans bounded repository files for high-entropy credential patterns (e.g., API keys,
private keys, bearer tokens) to prevent accidental credential leakage in synthetic fixtures,
datasets, and codebase files.

Logs strictly redact matched values to prevent credential exposure in CI output.
Note: Pattern scanning is an engineering safeguard, not a guarantee of zero leakage.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Bounded scanner rules
RULES: dict[str, re.Pattern[str]] = {
    "OPENAI_API_KEY": re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    "GOOGLE_API_KEY": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "GITHUB_PAT": re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{25,}\b"),
}

EXCLUDED_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".coverage",
    "build",
    "dist",
    "htmlcov",
}

EXCLUDED_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".zip",
    ".tar",
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".pdf",
}

DEFAULT_SCAN_TARGETS: tuple[str, ...] = (
    "src",
    "fixtures",
    "datasets",
    "tests",
    "scripts",
    ".github",
    "pyproject.toml",
    ".env.example",
)


@dataclass(frozen=True)
class ScanFinding:
    """Represents a detected secret pattern with redacted payload."""

    file_path: Path
    line_number: int
    rule_name: str

    def format_log(self, base_dir: Path | None = None) -> str:
        """Format finding for terminal output without exposing matched content."""
        display_path = (
            self.file_path.relative_to(base_dir)
            if base_dir and self.file_path.is_relative_to(base_dir)
            else self.file_path
        )
        return (
            f"[SECURITY SCAN ERROR] {display_path}:{self.line_number} "
            f"matched rule '{self.rule_name}' [CONTENT REDACTED]"
        )


def scan_file(path: Path) -> list[ScanFinding]:
    """Scan a single text file for credential patterns."""
    if path.suffix in EXCLUDED_EXTENSIONS:
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[ScanFinding] = []
    lines = content.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        for rule_name, pattern in RULES.items():
            if pattern.search(line):
                findings.append(
                    ScanFinding(
                        file_path=path,
                        line_number=line_idx,
                        rule_name=rule_name,
                    )
                )

    return findings


def scan_directory(
    target_dir: Path,
    explicit_targets: Sequence[str] | None = None,
) -> tuple[int, list[ScanFinding]]:
    """Scan all bounded target paths in target_dir.

    Args:
        target_dir: Base directory to scan.
        explicit_targets: Optional list of subpaths to scan. If omitted, uses default targets.

    Returns:
        Tuple of (total_files_scanned, list_of_findings).
    """
    targets_to_inspect: list[Path] = []

    if explicit_targets:
        for t in explicit_targets:
            p = target_dir / t if not Path(t).is_absolute() else Path(t)
            if p.exists():
                targets_to_inspect.append(p)
    else:
        for t in DEFAULT_SCAN_TARGETS:
            p = target_dir / t
            if p.exists():
                targets_to_inspect.append(p)

    files_to_scan: list[Path] = []
    for item in targets_to_inspect:
        if item.is_file():
            if item.suffix not in EXCLUDED_EXTENSIONS:
                files_to_scan.append(item)
        elif item.is_dir():
            for child in item.rglob("*"):
                if child.is_file():
                    # Check if any parent part is in EXCLUDED_DIRS
                    if any(part in EXCLUDED_DIRS for part in child.parts):
                        continue
                    if child.suffix not in EXCLUDED_EXTENSIONS:
                        files_to_scan.append(child)

    findings: list[ScanFinding] = []
    for f in files_to_scan:
        findings.extend(scan_file(f))

    return len(files_to_scan), findings


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for secret scanner."""
    parser = argparse.ArgumentParser(
        description="Scan repository files for sensitive credential patterns."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="Explicit subpaths/files to scan instead of default targets",
    )
    args = parser.parse_args(argv)

    root_path = Path(args.root).resolve()
    if not root_path.is_dir():
        print(f"[SECURITY SCAN ERROR] Target root is not a directory: {root_path}", file=sys.stderr)
        return 2

    files_count, findings = scan_directory(
        target_dir=root_path,
        explicit_targets=args.targets,
    )

    if findings:
        print(
            f"[SECURITY SCAN FAILED] Found {len(findings)} potential secret pattern(s) "
            f"across {files_count} scanned files:",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding.format_log(base_dir=root_path)}", file=sys.stderr)
        print(
            "\nRemediation: Remove raw credentials or sensitive tokens from repository files. "
            "Use environment variables or synthetic non-credential tokens for offline testing.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[SECURITY SCAN PASSED] Scanned {files_count} files in '{root_path.name}'. "
        "Zero credential patterns detected."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
