#!/usr/bin/env python3
"""
Japanese Kanji Vocab → Anki card importer.
Reads a CSV and adds cards to Anki Desktop via AnkiConnect.

Requirements:
  - Anki Desktop running with AnkiConnect add-on installed
  - pip install requests

Usage:
  python add_cards.py vocab.csv
  python add_cards.py vocab.csv --deck "Japanese::Kanji Vocab"
  python add_cards.py vocab.csv --dry-run
"""

import argparse
import csv
import re
import sys
import requests

ANKICONNECT_URL = "http://localhost:8765"
DEFAULT_DECK = "Japanese::Kanji Vocab"
NOTE_TYPE = "Japanese Kanji Vocab"

# ── CSV column names ──────────────────────────────────────────────────────────
COL_KANJI      = "kanji"        # e.g. 食べる
COL_READING    = "reading"      # e.g. たべる
COL_MEANING    = "meaning"      # e.g. to eat
COL_SENTENCE   = "sentence"     # e.g. 毎朝、朝食を食べます。(optional)
COL_TRANSLATION = "translation" # e.g. I eat breakfast every morning. (optional)
COL_TAGS       = "tags"         # e.g. N5,食 (optional, comma-separated)


def ankiconnect(action, **params):
    payload = {"action": action, "version": 6, "params": params}
    try:
        r = requests.post(ANKICONNECT_URL, json=payload, timeout=5)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to Anki. Make sure Anki Desktop is open and AnkiConnect is installed.")
        sys.exit(1)
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect error: {result['error']}")
    return result["result"]


def ensure_deck(deck_name):
    existing = ankiconnect("deckNames")
    if deck_name not in existing:
        ankiconnect("createDeck", deck=deck_name)
        print(f"Created deck: {deck_name}")


def ensure_note_type():
    """Create the note type if it doesn't exist yet."""
    existing = ankiconnect("modelNames")
    if NOTE_TYPE in existing:
        return

    ankiconnect(
        "createModel",
        modelName=NOTE_TYPE,
        inOrderFields=[
            "Kanji",
            "Reading",
            "Meaning",
            "Sentence",
            "Translation",
        ],
        css="""
.card { font-family: Arial, sans-serif; font-size: 18px; text-align: center; }
.kanji { font-size: 48px; color: #2c3e50; }
.reading { font-size: 22px; color: #7f8c8d; margin-top: 4px; }
.meaning { font-size: 20px; color: #27ae60; margin-top: 8px; }
.sentence { font-size: 16px; color: #34495e; margin-top: 16px; font-style: italic; }
.translation { font-size: 14px; color: #95a5a6; margin-top: 4px; }
.label { font-size: 11px; color: #bdc3c7; text-transform: uppercase; letter-spacing: 1px; }
        """,
        cardTemplates=[
            {
                # Card 1: Recognition — see kanji, recall reading + meaning
                "Name": "Recognition",
                "Front": '<div class="kanji">{{Kanji}}</div>',
                "Back": """
<div class="kanji">{{Kanji}}</div>
<hr>
<div class="reading">{{Reading}}</div>
<div class="meaning">{{Meaning}}</div>
{{#Sentence}}
<div class="sentence">{{Sentence}}</div>
{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}
{{/Sentence}}
                """,
            },
            {
                # Card 2: Production — see meaning in English, produce Japanese
                "Name": "Production",
                "Front": '<div class="label">How do you say:</div><div class="meaning" style="margin-top:12px">{{Meaning}}</div>',
                "Back": """
<div class="meaning">{{Meaning}}</div>
<hr>
<div class="kanji">{{Kanji}}</div>
<div class="reading">{{Reading}}</div>
{{#Sentence}}
<div class="sentence">{{Sentence}}</div>
{{#Translation}}<div class="translation">{{Translation}}</div>{{/Translation}}
{{/Sentence}}
                """,
            },
            {
                # Card 3: Reading — see kanji, produce reading only
                "Name": "Reading",
                "Front": '<div class="label">Reading:</div><div class="kanji" style="margin-top:8px">{{Kanji}}</div>',
                "Back": """
<div class="kanji">{{Kanji}}</div>
<hr>
<div class="reading">{{Reading}}</div>
<div class="meaning">{{Meaning}}</div>
                """,
            },
        ],
    )
    print(f"Created note type: {NOTE_TYPE}")


def build_note(row, deck_name):
    tags = []
    if row.get(COL_TAGS):
        tags = [t.strip() for t in row[COL_TAGS].split(",") if t.strip()]

    return {
        "deckName": deck_name,
        "modelName": NOTE_TYPE,
        "fields": {
            "Kanji":       row.get(COL_KANJI, "").strip(),
            "Reading":     row.get(COL_READING, "").strip(),
            "Meaning":     row.get(COL_MEANING, "").strip(),
            "Sentence":    strip_marker(row.get(COL_SENTENCE, "").strip()),
            "Translation": row.get(COL_TRANSLATION, "").strip(),
        },
        "tags": tags,
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
    }


def strip_marker(sentence):
    """Remove [ ] markers from sentence, keeping the text inside."""
    return re.sub(r"\[([^\]]+)\]", r"\1", sentence)


def validate_row(row, line_num):
    errors = []
    for required in (COL_KANJI, COL_READING, COL_MEANING):
        if not row.get(required, "").strip():
            errors.append(f"missing '{required}'")
    if errors:
        print(f"  Line {line_num}: SKIPPED — {', '.join(errors)}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Add Japanese kanji vocab cards to Anki.")
    parser.add_argument("csv_file", help="Path to your CSV file")
    parser.add_argument("--deck", default=DEFAULT_DECK, help=f"Target deck name (default: {DEFAULT_DECK})")
    parser.add_argument("--dry-run", action="store_true", help="Preview cards without adding to Anki")
    args = parser.parse_args()

    # Read CSV
    try:
        with open(args.csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"ERROR: File not found: {args.csv_file}")
        sys.exit(1)

    if not rows:
        print("ERROR: CSV file is empty.")
        sys.exit(1)

    print(f"Found {len(rows)} rows in {args.csv_file}")

    if args.dry_run:
        print("\n── DRY RUN (no cards will be added) ──\n")
        for i, row in enumerate(rows, start=2):
            if validate_row(row, i):
                note = build_note(row, args.deck)
                f = note["fields"]
                print(f"  [{i}] {f['Kanji']} ({f['Reading']}) — {f['Meaning']}")
                if f["Sentence"]:
                    print(f"       Sentence: {f['Sentence']}")
                if note["tags"]:
                    print(f"       Tags: {', '.join(note['tags'])}")
        print("\nDry run complete. Run without --dry-run to add cards.")
        return

    # Live run — connect to Anki
    print("Connecting to Anki...")
    ensure_deck(args.deck)
    ensure_note_type()

    added, skipped, duplicate, errored = 0, 0, 0, 0

    for i, row in enumerate(rows, start=2):
        if not validate_row(row, i):
            skipped += 1
            continue

        note = build_note(row, args.deck)
        kanji = note["fields"]["Kanji"]

        try:
            note_id = ankiconnect("addNote", note=note)
            if note_id:
                print(f"  ✓ Added: {kanji} ({note['fields']['Reading']}) — {note['fields']['Meaning']}")
                added += 1
            else:
                print(f"  ~ Duplicate skipped: {kanji}")
                duplicate += 1
        except RuntimeError as e:
            print(f"  ✗ Error on line {i} ({kanji}): {e}")
            errored += 1

    print(f"\n── Summary ──")
    print(f"  Added:      {added}")
    print(f"  Duplicates: {duplicate}")
    print(f"  Skipped:    {skipped}")
    print(f"  Errors:     {errored}")
    print(f"  Deck:       {args.deck}")


if __name__ == "__main__":
    main()
