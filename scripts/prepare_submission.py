"""Проверяет явные секреты и собирает ZIP файлов для публичного GitHub."""

import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parents[1] / "output"
PATTERNS = {
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    "OpenAI-style token": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "Yandex API key": re.compile(r"\bAQVN[A-Za-z0-9_-]{30,}\b"),
}


def main():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    files = sorted({p.decode("utf-8") for p in raw.split(b"\0") if p})
    findings = []
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue
        if name.startswith((".git/", "weights/", "data/", ".verification/", ".test-run")) or path.name == ".env":
            raise SystemExit("Private/runtime file selected: " + name)
        content = path.read_bytes()
        if b"\0" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append({"file": name, "line": text.count("\n", 0, match.start()) + 1, "kind": label})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"file_count": len(files), "credential_pattern_findings": findings,
              "scope": "Git-selected current files only. No remote history or personal-data certification.",
              "excluded": [".git", ".env", "weights", "data", ".verification", ".test-run*"]}
    (OUTPUT / "Проверка_файлов_GitHub.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if findings:
        # Значения найденных секретов никогда не выводятся.
        raise SystemExit(json.dumps(findings, ensure_ascii=False))
    destination = OUTPUT / "virtual-fitting-room_GitHub.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            if (ROOT / name).is_file():
                archive.write(ROOT / name, name)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        required = {"README.md", "app/main.py", "app/static/demo.html", "scripts/verify_real_tryon.py",
                    "docs/ASSIGNMENT_CHECKLIST.md", "docs/evidence/real-tryon.png"}
        assert required.issubset(archive.namelist())
    print(json.dumps({"files": len(files), "credential_pattern_findings": 0,
                      "archive": str(destination), "bytes": destination.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
