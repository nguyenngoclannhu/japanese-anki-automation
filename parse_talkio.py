#!/usr/bin/env python3
"""
Talkio transcript → Anki correction cards.

Parses a Talkio .txt transcript and extracts:
  1. Grammar/expression corrections  (User said X → Suggestion: Y)
  2. New vocabulary the tutor introduced that you hadn't used before

Then adds them to Anki Desktop via AnkiConnect.

Usage:
  python parse_talkio.py chat-7.txt
  python parse_talkio.py chat-7.txt --deck "Japanese::Talkio Corrections"
  python parse_talkio.py chat-7.txt --dry-run
"""

import argparse
import re
import sys
import requests

ANKICONNECT_URL = "http://localhost:8765"
DEFAULT_DECK = "Japanese::Talkio Corrections"
NOTE_TYPE_CORRECTION = "Talkio Correction"
NOTE_TYPE_VOCAB = "Talkio Vocab"


# ── AnkiConnect helpers ───────────────────────────────────────────────────────

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


def ensure_correction_note_type():
    if NOTE_TYPE_CORRECTION in ankiconnect("modelNames"):
        return
    ankiconnect(
        "createModel",
        modelName=NOTE_TYPE_CORRECTION,
        inOrderFields=["YourVersion", "NaturalVersion", "Context", "Note"],
        css="""
.card { font-family: Arial, sans-serif; font-size: 18px; text-align: center; padding: 20px; }
.label { font-size: 11px; color: #bdc3c7; text-transform: uppercase; letter-spacing: 1px; }
.wrong { font-size: 20px; color: #e74c3c; margin-top: 8px; }
.correct { font-size: 22px; color: #27ae60; margin-top: 12px; }
.context { font-size: 14px; color: #7f8c8d; margin-top: 16px; font-style: italic; border-top: 1px solid #ecf0f1; padding-top: 12px; }
.note { font-size: 13px; color: #95a5a6; margin-top: 8px; }
hr { border: none; border-top: 1px solid #ecf0f1; margin: 12px 0; }
        """,
        cardTemplates=[
            {
                # See your version → produce the natural version
                "Name": "Natural Expression",
                "Front": """
<div class="label">You said — how would a native say this?</div>
<div class="wrong">{{YourVersion}}</div>
                """,
                "Back": """
<div class="label">You said</div>
<div class="wrong">{{YourVersion}}</div>
<hr>
<div class="label">More natural</div>
<div class="correct">{{NaturalVersion}}</div>
{{#Context}}<div class="context">Context: {{Context}}</div>{{/Context}}
{{#Note}}<div class="note">{{Note}}</div>{{/Note}}
                """,
            }
        ],
    )
    print(f"Created note type: {NOTE_TYPE_CORRECTION}")


def ensure_vocab_note_type():
    if NOTE_TYPE_VOCAB in ankiconnect("modelNames"):
        return
    ankiconnect(
        "createModel",
        modelName=NOTE_TYPE_VOCAB,
        inOrderFields=["Word", "Reading", "Meaning", "ExampleFromSession"],
        css="""
.card { font-family: Arial, sans-serif; font-size: 18px; text-align: center; padding: 20px; }
.label { font-size: 11px; color: #bdc3c7; text-transform: uppercase; letter-spacing: 1px; }
.word { font-size: 40px; color: #2c3e50; margin-top: 8px; }
.reading { font-size: 20px; color: #7f8c8d; margin-top: 4px; }
.meaning { font-size: 18px; color: #27ae60; margin-top: 8px; }
.example { font-size: 15px; color: #34495e; margin-top: 16px; font-style: italic; }
hr { border: none; border-top: 1px solid #ecf0f1; margin: 12px 0; }
        """,
        cardTemplates=[
            {
                "Name": "Recognition",
                "Front": '<div class="word">{{Word}}</div>',
                "Back": """
<div class="word">{{Word}}</div>
<hr>
<div class="reading">{{Reading}}</div>
<div class="meaning">{{Meaning}}</div>
{{#ExampleFromSession}}<div class="example">{{ExampleFromSession}}</div>{{/ExampleFromSession}}
                """,
            }
        ],
    )
    print(f"Created note type: {NOTE_TYPE_VOCAB}")


# ── Transcript parsing ────────────────────────────────────────────────────────

def parse_transcript(text):
    """
    Extract correction pairs from the transcript.

    Talkio format:
      User: <what the user said>
      Suggestion: <corrected version>

    Returns a list of dicts:
      { user_text, suggestion, context }
    """
    corrections = []
    lines = text.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Strip leading line numbers if present (e.g. "12  User: ...")
        line = re.sub(r"^\d+\s+", "", line)

        if line.startswith("User:"):
            user_text = line[len("User:"):].strip()

            # Look ahead for a Suggestion on the next non-empty lines
            j = i + 1
            suggestion = None
            context_lines = []

            while j < len(lines):
                next_line = lines[j].strip()
                next_line_clean = re.sub(r"^\d+\s+", "", next_line)

                if next_line_clean.startswith("Suggestion:"):
                    suggestion = next_line_clean[len("Suggestion:"):].strip()
                    break
                elif next_line_clean.startswith("Tutor:") or next_line_clean.startswith("User:"):
                    # No suggestion before next speaker turn
                    break
                elif next_line_clean and not next_line_clean.startswith("Speech clarity"):
                    context_lines.append(next_line_clean)

                j += 1

            if suggestion and user_text != suggestion:
                corrections.append({
                    "user_text": user_text,
                    "suggestion": suggestion,
                    "context": " ".join(context_lines) if context_lines else "",
                })

        i += 1

    return corrections


def diff_summary(user_text, suggestion):
    """
    Find the first clause/phrase that differs between user_text and suggestion.
    Splits on Japanese punctuation and returns the first mismatched pair only,
    keeping the note concise and readable.
    """
    def split_clauses(text):
        return [c.strip() for c in re.split(r"[。、！？]", text) if c.strip()]

    user_clauses = split_clauses(user_text)
    sugg_clauses = split_clauses(suggestion)

    for u, s in zip(user_clauses, sugg_clauses):
        if u != s:
            return f"✗ {u}  →  ✓ {s}"

    # Lengths differ — surface the extra/missing clause
    if len(sugg_clauses) > len(user_clauses):
        return f"Added: {sugg_clauses[len(user_clauses)]}"
    if len(user_clauses) > len(sugg_clauses):
        return f"Removed: {user_clauses[len(sugg_clauses)]}"

    return ""


# ── Card building ─────────────────────────────────────────────────────────────

def build_correction_note(correction, deck_name, session_tag):
    note_text = diff_summary(correction["user_text"], correction["suggestion"])
    return {
        "deckName": deck_name,
        "modelName": NOTE_TYPE_CORRECTION,
        "fields": {
            "YourVersion":    correction["user_text"],
            "NaturalVersion": correction["suggestion"],
            "Context":        correction.get("context", ""),
            "Note":           note_text,
        },
        "tags": [session_tag, "correction"],
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse Talkio transcript and add correction cards to Anki.")
    parser.add_argument("transcript", help="Path to Talkio .txt transcript file")
    parser.add_argument("--deck", default=DEFAULT_DECK, help=f"Target deck (default: {DEFAULT_DECK})")
    parser.add_argument("--dry-run", action="store_true", help="Preview extractions without adding to Anki")
    parser.add_argument("--tag", default="talkio", help="Tag to apply to all cards (default: talkio)")
    args = parser.parse_args()

    try:
        with open(args.transcript, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"ERROR: File not found: {args.transcript}")
        sys.exit(1)

    corrections = parse_transcript(text)

    if not corrections:
        print("No corrections (User → Suggestion pairs) found in transcript.")
        return

    print(f"Found {len(corrections)} correction(s) in transcript.\n")

    if args.dry_run:
        print("── DRY RUN (no cards will be added) ──\n")
        for i, c in enumerate(corrections, 1):
            print(f"[{i}] You said:")
            print(f"     {c['user_text']}")
            print(f"     → Natural: {c['suggestion']}")
            note = diff_summary(c["user_text"], c["suggestion"])
            if note:
                print(f"     Note: {note}")
            print()
        print("Run without --dry-run to add cards.")
        return

    # Live run
    print("Connecting to Anki...")
    ensure_deck(args.deck)
    ensure_correction_note_type()

    added, duplicate, errored = 0, 0, 0

    for c in corrections:
        note = build_correction_note(c, args.deck, args.tag)
        try:
            note_id = ankiconnect("addNote", note=note)
            if note_id:
                print(f"  ✓ Added correction: {c['user_text'][:40]}...")
                added += 1
            else:
                print(f"  ~ Duplicate: {c['user_text'][:40]}...")
                duplicate += 1
        except RuntimeError as e:
            print(f"  ✗ Error: {e}")
            errored += 1

    print(f"\n── Summary ──")
    print(f"  Corrections added: {added}")
    print(f"  Duplicates:        {duplicate}")
    print(f"  Errors:            {errored}")
    print(f"  Deck:              {args.deck}")


if __name__ == "__main__":
    main()
