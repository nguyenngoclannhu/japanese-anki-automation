"""Export sheets from a .numbers file to per-sheet CSVs.

Configure the sheet → CSV mapping in a `.env` file next to this script:

    SHEET_MAP=Vocabulary=vocab.csv;Kanji Cloze=kanji_cloze.csv

The `.env` is loaded automatically. Override at runtime by setting SHEET_MAP
in the shell, e.g. `SHEET_MAP='A=a.csv' python export_numbers.py file.numbers`.

Usage:
    python export_numbers.py path/to/file.numbers

SHEET_MAP format: '<sheet name>=<output csv>;<sheet name>=<output csv>'
- Sheet names match exactly (case-sensitive) what's shown in Numbers.
- Output paths are relative to the .numbers file's directory unless absolute.
- Whitespace around names/paths is stripped.

Behavior:
- One table per sheet (the first one).
- First row written as the CSV header.
- Comma delimiter, csv.QUOTE_MINIMAL, UTF-8.
- Existing output files are overwritten.
- A name in SHEET_MAP that doesn't match any sheet is an error.
"""

import csv
import os
import sys
from pathlib import Path

from numbers_parser import Document


def load_dotenv(env_path: Path) -> None:
    """Load KEY=VALUE pairs from `env_path` into os.environ.

    Existing env vars take precedence (so a shell-set SHEET_MAP overrides .env).
    Tries python-dotenv first; falls back to a minimal parser if not installed.
    """
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv as _load
        _load(env_path, override=False)
        return
    except ImportError:
        pass

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ.setdefault(key, val)


def parse_sheet_map(raw: str) -> dict[str, str]:
    if not raw:
        sys.exit("SHEET_MAP not set. Define it in .env or as an env var.")
    mapping: dict[str, str] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            sys.exit(f"Invalid SHEET_MAP entry (missing '='): {entry!r}")
        name, out = entry.split("=", 1)
        name, out = name.strip(), out.strip()
        if not name or not out:
            sys.exit(f"Invalid SHEET_MAP entry (empty name or output): {entry!r}")
        mapping[name] = out
    if not mapping:
        sys.exit("SHEET_MAP parsed to empty mapping")
    return mapping


def export(numbers_path: Path, sheet_map: dict[str, str]) -> None:
    if not numbers_path.is_file():
        sys.exit(f"Not a file: {numbers_path}")

    doc = Document(str(numbers_path))
    sheets_by_name = {s.name: s for s in doc.sheets}

    missing = [name for name in sheet_map if name not in sheets_by_name]
    if missing:
        available = ", ".join(repr(n) for n in sheets_by_name)
        sys.exit(f"Sheet(s) not found: {missing}. Available: {available}")

    base_dir = numbers_path.parent
    for sheet_name, out_name in sheet_map.items():
        sheet = sheets_by_name[sheet_name]
        if not sheet.tables:
            sys.exit(f"Sheet {sheet_name!r} has no tables")
        table = sheet.tables[0]
        rows = list(table.rows(values_only=True))

        out_path = Path(out_name)
        if not out_path.is_absolute():
            out_path = base_dir / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            for row in rows:
                writer.writerow(["" if cell is None else cell for cell in row])

        print(f"  {sheet_name!r} -> {out_path} ({len(rows)} rows)")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    load_dotenv(script_dir / ".env")

    if len(sys.argv) != 2:
        sys.exit("Usage: python export_numbers.py <path/to/file.numbers>")
    numbers_path = Path(sys.argv[1]).expanduser().resolve()
    sheet_map = parse_sheet_map(os.environ.get("SHEET_MAP", ""))

    print(f"Exporting from {numbers_path}")
    export(numbers_path, sheet_map)
    print("Done.")


if __name__ == "__main__":
    main()
