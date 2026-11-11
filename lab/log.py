"""Append-only experiment log with a hash chain: each line carries sha256(previous sha + entry). Editing or deleting
a past line breaks verify(). The log holds ids, diffs and metrics, never prompts, transcripts or keys."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def path():
    return Path(getattr(settings, "CTXC_LAB_LOG", "") or Path(settings.BASE_DIR) / "var" / "lab" / "experiments.jsonl")


def _sha(prev, entry):
    return hashlib.sha256((prev + json.dumps(entry, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def read():
    p = path()
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def append(entry):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = read()
    prev = rows[-1]["sha"] if rows else "0" * 64
    entry = {"ts": timezone.now().isoformat(timespec="seconds"), **entry}
    row = {"prev": prev, "entry": entry, "sha": _sha(prev, entry)}
    with p.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def verify(rows=None):
    """-> (ok, index of the first bad line or None)"""
    prev = "0" * 64
    for i, row in enumerate(read() if rows is None else rows):
        if row["prev"] != prev or row["sha"] != _sha(prev, row["entry"]):
            return False, i
        prev = row["sha"]
    return True, None
