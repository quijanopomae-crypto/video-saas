from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("stripe_secret", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
)

GENERIC_QUOTED_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|
       jwt[_-]?secret|private[_-]?token|password)\b
    [ \t]*[:=][ \t]*
    (["'])([^"'\r\n]{16,})\2
    """
)
GENERIC_ENV_ASSIGNMENT = re.compile(
    r"""(?imx)
    ^\s*(?:export\s+)?
    ([A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|CLIENT_SECRET|JWT_SECRET|PASSWORD))
    [ \t]*=[ \t]*([^\s#]{16,})[ \t]*$
    """
)

PLACEHOLDER_MARKERS = (
    "example",
    "test-only",
    "test_only",
    "fake",
    "dummy",
    "not-valid",
    "not_valid",
    "changeme",
    "placeholder",
)

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".toml",
    ".ini",
    ".ps1",
    ".sh",
}
ALLOWED_ENV_FILES = {".env.example", ".env.template", ".env.sample"}


def is_forbidden_env_path(rel: str) -> bool:
    name = Path(rel).name
    return name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_FILES)


def _placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def scan_text(text: str) -> list[str]:
    findings: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(name)
    for match in GENERIC_QUOTED_ASSIGNMENT.finditer(text):
        if not _placeholder(match.group(3)):
            findings.append(f"generic_{match.group(1).lower().replace('-', '_')}")
    for match in GENERIC_ENV_ASSIGNMENT.finditer(text):
        if not _placeholder(match.group(2)):
            findings.append(f"generic_{match.group(1).lower()}")
    return sorted(set(findings))


def scan_tracked_file(rel: str, path: Path) -> list[str]:
    if is_forbidden_env_path(rel):
        return ["tracked_env_file"]
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
        ".env.example",
        ".env.template",
        ".env.sample",
        ".gitignore",
    }:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    return scan_text(text)


def tracked_files(root: Path = ROOT) -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [
        item.decode("utf-8", "surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]


def main() -> int:
    violations: list[tuple[str, str]] = []
    for rel in tracked_files(ROOT):
        path = ROOT / rel
        for finding in scan_tracked_file(rel, path):
            violations.append((rel, finding))

    if violations:
        print("POTENTIAL_SECRET_FOUND")
        for rel, finding in sorted(set(violations)):
            print(f"{rel}: {finding}")
        return 2

    print("SECRET_HYGIENE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
