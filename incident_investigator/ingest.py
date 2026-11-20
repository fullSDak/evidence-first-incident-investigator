"""Read local evidence without executing, importing, or trusting its contents."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".jsonl", ".ndjson", ".log", ".txt", ".csv"}
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_RECORDS = 10_000


class InputError(ValueError):
    """The supplied evidence cannot be ingested safely and reproducibly."""


def _source_files(path: Path) -> tuple[Path, list[Path]]:
    if path.is_symlink():
        raise InputError("A symlink cannot be used as the input path")
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise InputError(f"Unsupported input extension: {path.suffix}")
        return path.parent, [path]
    if not path.is_dir():
        raise InputError(f"Input is not an existing file or directory: {path}")
    # Refuse symlinks instead of following them or silently omitting data.
    files: list[Path] = []
    for item in path.rglob("*"):
        if item.is_symlink():
            raise InputError(f"Symlinks are not supported in the input tree: {item}")
        if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(item)
    files.sort(key=lambda p: p.relative_to(path).as_posix())
    if not files:
        raise InputError("No supported evidence files found")
    return path, files


def _evidence_id(source: str, number: int, text: str) -> str:
    # Length-prefixed JSON avoids delimiter ambiguity; path is case-root relative.
    identity = json.dumps([source, number, text], ensure_ascii=False, separators=(",", ":"))
    return "E-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _deployment_source(source: str) -> bool:
    return "deploy" in source.lower()


def _make_record(source: str, number: int, text: str, kind: str,
                 data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": _evidence_id(source, number, text), "source": source,
            "line": number, "text": text, "kind": kind, "data": data}


def _json_object(line: str) -> dict[str, Any] | None:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        value = json.loads(line, object_pairs_hook=unique_object, parse_constant=reject_constant)
        # An otherwise valid huge exponent may decode to infinity in Python.
        json.dumps(value, allow_nan=False)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _csv_row(line: str, source: str, number: int) -> list[str]:
    try:
        # One CSV row per physical line. Embedded newlines are deliberately unsupported.
        return next(csv.reader(io.StringIO(line, newline=""), strict=True))
    except (csv.Error, StopIteration) as exc:
        raise InputError(f"Invalid one-line CSV row at {source}:{number}") from exc


def load_evidence(input_path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return all physical nonblank lines, preserving exact line numbers and text.

    CSV headers are evidence too. Row records carry ``context_ids`` referencing
    their header, which must accompany any field-derived citation. Invalid JSONL
    remains visible evidence but is never interpreted as structured JSON fields.
    """
    root, files = _source_files(Path(input_path).expanduser())
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    ids: set[str] = set()
    for path in files:
        source = path.relative_to(root).as_posix()
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise InputError(f"File exceeds {MAX_FILE_BYTES} bytes: {source}")
            # newline='' preserves CR/LF distinctions; splitlines below removes only line endings.
            with path.open("r", encoding="utf-8", newline="") as stream:
                lines = stream.readlines()
        except (OSError, UnicodeError) as exc:
            raise InputError(f"Cannot read UTF-8 evidence file: {source}") from exc
        csv_header: list[str] | None = None
        header_id: str | None = None
        for number, physical_line in enumerate(lines, 1):
            line = physical_line.removesuffix("\n").removesuffix("\r")
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                raise InputError(f"Line exceeds {MAX_LINE_BYTES} bytes: {source}:{number}")
            if not line.strip():
                continue
            suffix = path.suffix.lower()
            data: dict[str, Any] | None = None
            kind = "deployment" if _deployment_source(source) else "log"
            if suffix == ".csv":
                row = _csv_row(line, source, number)
                if csv_header is None:
                    if not row or any(not x.strip() for x in row) or len(set(row)) != len(row):
                        raise InputError(f"CSV needs unique nonempty column names: {source}:{number}")
                    csv_header = row
                    rec = _make_record(source, number, line, "csv_header")
                    header_id = rec["id"]
                else:
                    if len(row) != len(csv_header):
                        raise InputError(f"CSV row has wrong number of columns: {source}:{number}")
                    data = dict(zip(csv_header, row))
                    rec = _make_record(source, number, line, kind, data)
                    rec["context_ids"] = [header_id]
            else:
                data = _json_object(line)
                if suffix in {".jsonl", ".ndjson"} and data is None:
                    warnings.append(f"Not a JSON object; retained as unparsed evidence: {source}:{number}")
                if data is not None:
                    record_type = data.get("record_type", data.get("type", ""))
                    if isinstance(record_type, str) and record_type.lower() in {"deployment", "deploy"}:
                        kind = "deployment"
                rec = _make_record(source, number, line, kind, data)
            if rec["id"] in ids:
                raise InputError("Evidence identifier collision; aborting rather than merging records")
            ids.add(rec["id"])
            records.append(rec)
            if len(records) > MAX_RECORDS:
                raise InputError(f"Case exceeds {MAX_RECORDS} nonblank evidence lines")
    if not records:
        raise InputError("Evidence files contain no nonblank lines")
    return records, warnings
