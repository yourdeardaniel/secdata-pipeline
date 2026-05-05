"""
Storage utilities for the conversion pipeline.

These deal exclusively with reading/writing JSONL files and managing
checkpoint state. There's no scraping or compliance logic here —
the pipeline doesn't make outbound HTTP requests.
"""
import hashlib
import json
import os
from typing import List


def ensure_dirs(*paths) -> None:
    """Create one or more directories, ignoring already-existing ones."""
    for p in paths:
        if p:
            os.makedirs(p, exist_ok=True)


def load_jsonl(path: str) -> list:
    """
    Read a JSONL file into a list of dicts.
    Returns [] if the file doesn't exist. Skips malformed lines silently.
    """
    if not os.path.exists(path):
        return []
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return docs


def save_jsonl(path: str, docs: List[dict]) -> None:
    """Overwrite a JSONL file with the given documents."""
    ensure_dirs(os.path.dirname(os.path.abspath(path)))
    with open(path, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def append_jsonl(path: str, docs: List[dict]) -> None:
    """Append documents to a JSONL file, creating the file if needed."""
    if not docs:
        return
    ensure_dirs(os.path.dirname(os.path.abspath(path)))
    with open(path, "a", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def count_lines(path: str) -> int:
    """Count newlines in a file. Returns 0 if file doesn't exist."""
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def load_checkpoint(path: str) -> dict:
    """
    Load a JSON checkpoint file.
    Returns {} on missing file, malformed JSON, or read error.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_checkpoint(path: str, data: dict) -> None:
    """
    Atomically save checkpoint state.

    Writes to a temp file then renames, so a crash mid-write
    doesn't corrupt the existing checkpoint.
    """
    ensure_dirs(os.path.dirname(os.path.abspath(path)))
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)


def stable_doc_id(doc: dict) -> str:
    """
    Deterministic document ID.

    Tries url, id, file fields in order. Falls back to a hash of the
    first 200 characters of text. Used for resuming converter runs
    across restarts — Python's built-in hash() returns different
    values per process so isn't safe for persistence.
    """
    return (
        doc.get("url")
        or doc.get("id")
        or doc.get("file", "")
        or "txt:" + hashlib.md5(
            doc.get("text", "")[:200].encode("utf-8")
        ).hexdigest()[:16]
    )
