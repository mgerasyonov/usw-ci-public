from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLIC_PAYLOAD_MANIFEST.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allowed = set(manifest["files"])

    actual = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        actual.add(rel)

    unexpected = sorted(actual - allowed)
    missing = sorted(allowed - actual)

    if unexpected or missing:
        print("PUBLIC_PAYLOAD_SCAN=FAIL")
        for item in unexpected:
            print(f"unexpected file: {item}")
        for item in missing:
            print(f"missing file: {item}")
        return 1

    for rel in sorted(actual):
        path = ROOT / rel
        if path.stat().st_size > 250_000:
            print("PUBLIC_PAYLOAD_SCAN=FAIL")
            print(f"oversized file: {rel}")
            return 1
        path.read_text(encoding="utf-8")

    print("PUBLIC_PAYLOAD_SCAN=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
