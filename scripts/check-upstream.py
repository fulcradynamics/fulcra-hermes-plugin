#!/usr/bin/env python3
"""Report what changed upstream since the skills here were adapted.

The skills are adapted from the Claude Fulcra plugin
(fulcradynamics/claude-plugin), which adapts them from the ChatGPT plugin.
provenance.json records, for each file, its source path and the sha256 of the
source content it was adapted from. Adapted files are rewritten for Hermes, so
they are never copied over; this lists which sources changed so someone can
port the changes by hand. Verbatim files must match their source exactly.

Comparisons use those content hashes, not git history.

    scripts/check-upstream.py <Claude plugin checkout>             # its origin/main
    scripts/check-upstream.py <Claude plugin checkout> <ref>       # another ref
    scripts/check-upstream.py <Claude plugin checkout> <ref> --repin   # after porting

Upstream skill files that nothing here comes from are reported too, unless
provenance.json lists them under "ignored_upstream" with the reason.

Exits 0 when nothing changed and every check passes, 1 otherwise. --repin
records <ref> and the current content hash of every source.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVENANCE = ROOT / "provenance.json"
# Upstream files the skills are built from live here.
SOURCE_DIR = "plugins/fulcra/skills/"


def git(checkout: str, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", checkout, *args], capture_output=True, check=True
    ).stdout


def source_at(checkout: str, ref: str, path: str) -> bytes | None:
    try:
        return git(checkout, "show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    args = sys.argv[1:]
    repin = "--repin" in args
    args = [a for a in args if a != "--repin"]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    checkout = args[0]
    ref = args[1] if len(args) > 1 else "origin/main"
    doc = json.loads(PROVENANCE.read_text())
    new = git(checkout, "rev-parse", ref).decode().strip()
    problems = 0

    entries = {ours: e for ours, e in doc["files"].items() if e.get("source")}
    for ours, entry in entries.items():
        source = entry["source"]
        if entry["mode"] == "verbatim" and sha256((ROOT / ours).read_bytes()) != entry["sha256"]:
            print(f"verbatim copy differs from its recorded source: {ours}")
            problems += 1
        at_ref = source_at(checkout, new, source)
        if at_ref is None:
            print(f"removed upstream: {source} (used by {ours})")
            problems += 1
        elif sha256(at_ref) != entry["sha256"]:
            print(f"changed upstream: {source} -> review {ours}")
            problems += 1

    # Upstream skill files that nothing here is adapted from yet.
    tracked = {e["source"] for e in entries.values()} | set(doc.get("ignored_upstream", {}))
    listed = git(checkout, "ls-tree", "-r", "--name-only", new, SOURCE_DIR).decode().split()
    for path in sorted(set(listed) - tracked):
        print(f"new upstream, not adapted: {path}")
        problems += 1

    if repin:
        for entry in entries.values():
            data = source_at(checkout, new, entry["source"])
            if data is not None:
                entry["sha256"] = sha256(data)
        doc["upstream"]["commit"] = new
        doc["upstream"].pop("note", None)
        PROVENANCE.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"repinned to {new}")
        return 0

    if not problems:
        print(f"nothing to port: sources match {new[:9]}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
