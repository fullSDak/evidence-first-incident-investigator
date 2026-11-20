"""CLI for reproducible offline investigations and explicitly opted-in LLM analysis."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .ingest import SUPPORTED_SUFFIXES
from .investigation import investigate
from .llm import LLMError
from .report import render_markdown


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="incident-investigator", description="Investigate untrusted incident records with line-level evidence citations.")
    parser.add_argument("--input", "--case", dest="input_path", required=True,
                        help="Evidence file or case directory; --case is an alias for --input")
    parser.add_argument("--mode", choices=("offline", "llm"), default="offline",
                        help="offline (default) is fully deterministic; llm sends evidence to the configured provider")
    parser.add_argument("--output", help="Write Markdown to this file rather than standard output")
    return parser


def _check_output(input_path: str, output_path: str) -> Path:
    inp = Path(input_path).expanduser()
    out = Path(output_path).expanduser()
    if out.is_symlink():
        raise ValueError("Output must not be a symlink")
    input_resolved, output_resolved = inp.resolve(), out.resolve()
    if inp.is_file() and input_resolved == output_resolved:
        raise ValueError("Output cannot overwrite the evidence input")
    if inp.is_dir() and output_resolved.is_relative_to(input_resolved) and out.suffix.lower() in SUPPORTED_SUFFIXES:
        raise ValueError("Output within the input directory must not have an evidence-file extension")
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = _check_output(args.input_path, args.output) if args.output else None
        result = investigate(args.input_path, args.mode)
        markdown = render_markdown(result)
        if output is None:
            sys.stdout.write(markdown)
        else:
            output.write_text(markdown, encoding="utf-8")
    except (ValueError, OSError, LLMError) as exc:
        print(f"incident-investigator: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
