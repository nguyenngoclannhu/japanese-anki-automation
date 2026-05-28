#!/usr/bin/env python3
"""
Vocabulary cloze card importer for Anki.
Reads a CSV and adds cloze deletion cards via AnkiConnect, using Anki's
built-in "Cloze" note type.

One CSV row = one Anki note = 3 cards:
  c1 — kanji
  c2 — reading
  c3 — meaning

The example sentence (with [marker] stripped) and translation are rendered
in a fixed paragraph location on every card so downstream automation
(e.g. TTS, screenshotting) can reliably target them.

Rows without a sentence are skipped entirely.

Requirements:
  - Anki Desktop running with AnkiConnect add-on installed
  - pip install requests

Usage:
  python add_cards.py vocab.csv
  python add_cards.py vocab.csv --deck "Japanese::Vocab Cloze"
  python add_cards.py vocab.csv --dry-run
"""

import argparse
import csv
import re
import sys
import requests

ANKICONNECT_URL = "http://localhost:8765"
DEFAULT_DECK = "Japanese::Vocab Cloze"
NOTE_TYPE = "Cloze"

# ── CSV column names ──────────────────────────────────────────────────────────
COL_KANJI       = "kanji"
COL_READING     = "reading"
COL_MEANING     = "meaning"
COL_SENTENCE    = "sentence"
COL_TRANSLATION = "translation"
COL_TAGS        = "tags"


# ── AnkiConnect ───────────────────────────────────────────────────────────────

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
    if deck_name not in ankiconnect("deckNames"):
        ankiconnect("createDeck", deck=deck_name)
        print(f"Created deck: {deck_name}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_marker(sentence):
    """Remove [ ] markers from sentence, keeping the text inside."""
    return re.sub(r"\[([^\]]+)\]", r"\1", sentence)


def validate_row(row, line_num):
    missing = []
    for col in (COL_KANJI, COL_READING, COL_MEANING):
        if not row.get(col, "").strip():
            missing.append(col)
    if missing:
        print(f"  Line {line_num}: SKIPPED — missing: {', '.join(missing)}")
        return False
    if not row.get(COL_SENTENCE, "").strip():
        print(f"  Line {line_num}: SKIPPED — no sentence ({row.get(COL_KANJI, '').strip()})")
        return False
    return True


def build_text(row):
    """
    Build the HTML for the Cloze note's Text field.

    Layout (consistent across every card so automation can target by class):
      .vocab-word     → c1 (kanji)
      .vocab-reading  → c2 (reading)
      .vocab-meaning  → c3 (meaning)
      .sentence       → example sentence (no cloze, marker stripped)
      .translation    → English translation (optional)
    """
    kanji       = row[COL_KANJI].strip()
    reading     = row[COL_READING].strip()
    meaning     = row[COL_MEANING].strip()
    sentence    = strip_marker(row[COL_SENTENCE].strip())
    translation = row.get(COL_TRANSLATION, "").strip()

    translation_html = (
        f'<div class="translation">{translation}</div>' if translation else ""
    )

    return (
        f'<div class="vocab-block">'
        f'<div class="vocab-word">{{{{c1::{kanji}}}}}</div>'
        f'<div class="vocab-reading">{{{{c2::{reading}}}}}</div>'
        f'<div class="vocab-meaning">{{{{c3::{meaning}}}}}</div>'
        f'</div>'
        f'<div class="sentence-block">'
        f'<div class="sentence">{sentence}</div>'
        f'{translation_html}'
        f'</div>'
    )


def build_cloze_note(row, deck_name):
    tags = [t.strip() for t in row.get(COL_TAGS, "").split(",") if t.strip()]

    return {
        "deckName": deck_name,
        "modelName": NOTE_TYPE,
        "fields": {
            "Text": build_text(row),
            "Back Extra": "",
        },
        "tags": tags,
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add Japanese vocab cloze cards to Anki.")
    parser.add_argument("csv_file", help="Path to your CSV file")
    parser.add_argument("--deck", default=DEFAULT_DECK, help=f"Target deck name (default: {DEFAULT_DECK})")
    parser.add_argument("--dry-run", action="store_true", help="Preview cards without adding to Anki")
    args = parser.parse_args()

    try:
        with open(args.csv_file, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
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
            if not validate_row(row, i):
                continue
            note = build_cloze_note(row, args.deck)
            print(f"  [{i}] {row[COL_KANJI]} ({row[COL_READING]}) — {row[COL_MEANING]}")
            print(f"       Sentence: {strip_marker(row[COL_SENTENCE].strip())}")
            if note["tags"]:
                print(f"       Tags: {', '.join(note['tags'])}")
            print(f"       Text: {note['fields']['Text']}")
        print("\nDry run complete. Run without --dry-run to add cards.")
        return

    print("Connecting to Anki...")
    ensure_deck(args.deck)

    added, duplicate, skipped, errored = 0, 0, 0, 0

    for i, row in enumerate(rows, start=2):
        if not validate_row(row, i):
            skipped += 1
            continue

        note = build_cloze_note(row, args.deck)
        kanji = row[COL_KANJI].strip()

        try:
            note_id = ankiconnect("addNote", note=note)
            if note_id:
                print(f"  ✓ Added: {kanji} ({row[COL_READING]}) — 3 cards")
                added += 1
            else:
                print(f"  ~ Duplicate skipped: {kanji}")
                duplicate += 1
        except RuntimeError as e:
            print(f"  ✗ Error on line {i} ({kanji}): {e}")
            errored += 1

    print(f"\n── Summary ──")
    print(f"  Notes added:  {added}  ({added * 3} cards total)")
    print(f"  Duplicates:   {duplicate}")
    print(f"  Skipped:      {skipped}")
    print(f"  Errors:       {errored}")
    print(f"  Deck:         {args.deck}")


if __name__ == "__main__":
    main()
