#!/usr/bin/env python3
"""
Kanji cloze card importer for Anki.
Reads kanji_cloze.csv and adds cloze deletion cards via AnkiConnect.

One CSV row = one Anki note = 8 cards:
  c1 — kanji character
  c2 — kanji reading
  c3 — vocab_1 blanked in sentence_1
  c4 — reading_1
  c5 — meaning_1
  c6 — vocab_2 blanked in sentence_2
  c7 — reading_2
  c8 — meaning_2

Requirements:
  - Anki Desktop open with AnkiConnect add-on (code: 2055492159)
  - pip install requests

Usage:
  python3 add_kanji_cloze.py kanji_cloze.csv
  python3 add_kanji_cloze.py kanji_cloze.csv --deck "Japanese::Kanji Cloze"
  python3 add_kanji_cloze.py kanji_cloze.csv --dry-run
"""

import argparse
import csv
import re
import sys
import requests

ANKICONNECT_URL = "http://localhost:8765"
DEFAULT_DECK = "Japanese::Kanji Cloze"
NOTE_TYPE = "Japanese Kanji Cloze"

CSS = """
.card {
  font-family: Arial, sans-serif;
  font-size: 18px;
  text-align: left;
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.8;
}
.kanji-header {
  font-size: 52px;
  text-align: center;
  color: #2c3e50;
  margin-bottom: 4px;
}
.meaning-header {
  font-size: 16px;
  text-align: center;
  color: #7f8c8d;
  margin-bottom: 20px;
}
.label {
  font-size: 11px;
  color: #bdc3c7;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 16px;
  margin-bottom: 2px;
}
.reading { font-size: 22px; color: #2980b9; }
.vocab-block {
  border-left: 3px solid #ecf0f1;
  padding-left: 12px;
  margin-top: 12px;
}
.vocab-word { font-size: 22px; color: #2c3e50; }
.vocab-reading { font-size: 16px; color: #7f8c8d; }
.vocab-meaning { font-size: 16px; color: #27ae60; }
.sentence { font-size: 17px; color: #34495e; margin-top: 6px; }
.cloze { font-weight: bold; color: #e67e22; }
hr { border: none; border-top: 1px solid #ecf0f1; margin: 16px 0; }
"""

FRONT_BACK = """
<div class="kanji-header">{{Kanji}}</div>
<div class="meaning-header">{{Meaning}}</div>
<hr>

<div class="label">Reading</div>
<div class="reading">{{Reading}}}}</div>

<hr>

<div class="label">Vocabulary 1</div>
<div class="vocab-block">
  <div class="vocab-word">{{Vocab1}}</div>
  <div class="vocab-reading">{{Reading1}}</div>
  <div class="vocab-meaning">{{Meaning1}}</div>
  <div class="sentence">{{Sentence1}}</div>
</div>

<div class="label">Vocabulary 2</div>
<div class="vocab-block">
  <div class="vocab-word">{{c6::{{Vocab2}}}}</div>
  <div class="vocab-reading">{{c7::{{Reading2}}}}</div>
  <div class="vocab-meaning">{{c8::{{Meaning2}}}}</div>
  <div class="sentence">{{Sentence2}}</div>
</div>
"""


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


def ensure_note_type():
    if NOTE_TYPE in ankiconnect("modelNames"):
        return

    ankiconnect(
        "createModel",
        modelName=NOTE_TYPE,
        inOrderFields=[
            "Kanji", "Meaning", "Reading",
            "Vocab1", "Reading1", "Meaning1", "Sentence1",
            "Vocab2", "Reading2", "Meaning2", "Sentence2",
        ],
        isCloze=True,
        css=CSS,
        cardTemplates=[
            {
                "Name": "Kanji Cloze",
                "Front": "{{furigana:cloze:Text}}",
                "Back":  "{{furigana:cloze:Text}}<br>\n{{Back Extra}}",
            }
        ],
    )
    print(f"Created note type: {NOTE_TYPE}")


# ── CSV helpers ───────────────────────────────────────────────────────────────

REQUIRED = ["kanji", "meaning", "reading",
            "vocab_1", "reading_1", "meaning_1", "sentence_1",
            "vocab_2", "reading_2", "meaning_2", "sentence_2"]


def validate_row(row, line_num):
    missing = [c for c in REQUIRED if not row.get(c, "").strip()]
    if missing:
        print(f"  Line {line_num}: SKIPPED — missing: {', '.join(missing)}")
        return False
    return True


def inject_cloze(sentence, cloze_num):
    """
    Replace **marked text** in sentence with {{cN::marked text}}.
    The marker ** ** is written by the user in the CSV to explicitly mark
    which word should be blanked — no stem guessing needed.
    Raises ValueError if no marker is found.
    """
    print(sentence)
    match = re.search(r"\*\*([^\*\*]+)\*\*", sentence)
    if not match:
        raise ValueError(f"No **marker** found in sentence: {sentence!r}")
    inner = match.group(1)
    return sentence[:match.start()] + f"{{{{c{cloze_num}::{inner}}}}}" + sentence[match.end():]


def build_note(row, deck_name):
    tags = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]

    sentence_1 = inject_cloze(row["sentence_1"].strip(), 3)
    sentence_2 = inject_cloze(row["sentence_2"].strip(), 6)

    return {
        "deckName": deck_name,
        "modelName": NOTE_TYPE,
        "fields": {
            "Kanji":    f"{{{{c1::{row['kanji'].strip()}}}}}",
            "Meaning":  row["meaning"].strip(),
            "Reading":  f"{{{{c2::{row['reading'].strip()}}}}}",
            "Vocab1":   f"{{{{c3::{row['vocab_1'].strip()}}}}}",
            "Reading1": f"{{{{c4::{row['reading_1'].strip()}}}}}",
            "Meaning1": f"{{{{c5::{row['meaning_1'].strip()}}}}}",
            "Sentence1": sentence_1,
            "Vocab2":   f"{{{{c6::{row['vocab_2'].strip()}}}}}",
            "Reading2": f"{{{{c7::{row['reading_2'].strip()}}}}}",
            "Meaning2": f"{{{{c8::{row['meaning_2'].strip()}}}}}",
            "Sentence2": sentence_2,
        },
        "tags": tags,
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
    }

def build_text(row):
    sentence_1 = inject_cloze(row["sentence_1"].strip(), 3)
    sentence_2 = inject_cloze(row["sentence_2"].strip(), 6)
    Kanji=f"c1::{row['kanji'].strip()}"
    Meaning= f"c9::{row['meaning'].strip()}"
    Reading = f"c2::{row['reading'].strip()}"
    Vocab1 = f"c3::{row['vocab_1'].strip()}"
    Reading1 = f"c4::{row['reading_1'].strip()}"
    Meaning1 = f"c5::{row['meaning_1'].strip()}"
    Sentence1 = sentence_1
    Vocab2 = f"c6::{row['vocab_2'].strip()}"
    Reading2= f"c7::{row['reading_2'].strip()}"
    Meaning2= f"c8::{row['meaning_2'].strip()}"
    Sentence2 = sentence_2
    
    template = f"""
    <div class="kanji-header">{{{{{Kanji}}}}}</div>
    <div class="meaning-header">{{{{{Meaning}}}}}</div>
    <hr>

    <div class="label">Reading</div>
    <div class="reading">{{{{{Reading}}}}}</div>

    <hr>

    <div class="label">Vocabulary 1</div>
    <div class="vocab-block">
    <div class="vocab-word">{{{{{Vocab1}}}}}</div>
    <div class="vocab-reading">{{{{{Reading1}}}}}</div>
    <div class="vocab-meaning">{{{{{Meaning1}}}}}</div>
    <div class="sentence">{Sentence1}</div>
    </div>

    <div class="label">Vocabulary 2</div>
    <div class="vocab-block">
    <div class="vocab-word">{{{{{Vocab2}}}}}</div>
    <div class="vocab-reading">{{{{{Reading2}}}}}</div>
    <div class="vocab-meaning">{{{{{Meaning2}}}}}</div>
    <div class="sentence">{Sentence2}</div>
    </div>
    """
    return template

    

def build_cloze_note(row, deck_name):
    tags = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]

    return {
        "deckName": deck_name,
        "modelName": "Cloze",
        "fields": {
            "Text": build_text(row),
            "Back Extra": ""
        },
        "tags": tags,
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
    }    


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add kanji cloze cards to Anki.")
    parser.add_argument("csv_file", help="Path to kanji_cloze.csv")
    parser.add_argument("--deck", default=DEFAULT_DECK, help=f"Target deck (default: {DEFAULT_DECK})")
    parser.add_argument("--dry-run", action="store_true", help="Preview without adding to Anki")
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

    print(f"Found {len(rows)} kanji in {args.csv_file}")

    if args.dry_run:
        print("\n── DRY RUN (no cards will be added) ──\n")
        for i, row in enumerate(rows, start=2):
            if not validate_row(row, i):
                continue
            note = build_cloze_note(row, args.deck)
            f = note["fields"]
            # print(f"  Kanji:    {row['kanji']} ({row['reading']}) — {row['meaning']}")
            # print(f"  Vocab 1:  {row['vocab_1']} ({row['reading_1']}) — {row['meaning_1']}")
            # print(f"  Sent  1:  {f['Sentence1']}")
            # print(f"  Vocab 2:  {row['vocab_2']} ({row['reading_2']}) — {row['meaning_2']}")
            # print(f"  Sent  2:  {f['Sentence2']}")
            # print(f"  Tags:     {', '.join(note['tags']) or '—'}")
            # print(f"  Cards:    c1 kanji · c2 reading · c3-c5 vocab1 · c6-c8 vocab2")
            print(f)
        print("Run without --dry-run to add cards.")
        return

    print("Connecting to Anki...")
    ensure_deck(args.deck)
    ensure_note_type()

    added, duplicate, skipped, errored = 0, 0, 0, 0

    for i, row in enumerate(rows, start=2):
        if not validate_row(row, i):
            skipped += 1
            continue

        note = build_cloze_note(row, args.deck)
        kanji = row["kanji"]

        try:
            note_id = ankiconnect("addNote", note=note)
            if note_id:
                print(f"  ✓ Added: {kanji} ({row['reading']}) — 8 cards")
                added += 1
            else:
                print(f"  ~ Duplicate skipped: {kanji}")
                duplicate += 1
        except RuntimeError as e:
            print(f"  ✗ Error on line {i} ({kanji}): {e}")
            errored += 1

    print(f"\n── Summary ──")
    print(f"  Kanji added:  {added}  ({added * 8} cards total)")
    print(f"  Duplicates:   {duplicate}")
    print(f"  Skipped:      {skipped}")
    print(f"  Errors:       {errored}")
    print(f"  Deck:         {args.deck}")


if __name__ == "__main__":
    main()
