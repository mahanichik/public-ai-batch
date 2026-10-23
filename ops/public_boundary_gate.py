"""Fail closed if this public runner starts acquiring private project access."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = [
    (re.compile(r"mahanichik/VianaPulse(?:\\b|/)", re.I), "private repository reference"),
    (re.compile(r"(?i)(?:ghp_|github_pat_|gho_|ghu_|ghs_)[A-Za-z0-9_]{15,}"), "GitHub credential"),
    (re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
]
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}
SUFFIXES = {".py", ".js", ".ts", ".json", ".yml", ".yaml", ".md", ".toml", ".sh"}
issues = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(p in EXCLUDED for p in path.relative_to(ROOT).parts):
        continue
    if path == Path(__file__).resolve() or path.suffix.lower() not in SUFFIXES or path.stat().st_size > 2_000_000:
        continue
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeError:
        continue
    for pattern, label in BLOCKED:
        if pattern.search(content):
            issues.append(f"{path.relative_to(ROOT)}: {label}")
if issues:
    print("PUBLIC BOUNDARY FAILED:")
    print("\n".join(issues))
    sys.exit(1)
print("PUBLIC BOUNDARY PASS: no known private-repo reference or credential patterns found")
