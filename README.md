# Japanese Anki Automation

Automatically add Japanese kanji vocab cards to Anki Desktop from a CSV file.

---

## Setup (One Time)

### 1. Install AnkiConnect in Anki Desktop
1. Open Anki Desktop
2. Go to **Tools → Add-ons → Get Add-ons**
3. Enter code: `2055492159`
4. Restart Anki

### 2. Install Python dependency
```bash
pip install requests
```

---

## CSV Format

Fill in `vocab.csv` (or create your own file):

| Column | Required | Description |
|---|---|---|
| `kanji` | Yes | The word (e.g. 食べる) |
| `reading` | Yes | Hiragana reading (e.g. たべる) |
| `meaning` | Yes | English meaning (e.g. to eat) |
| `sentence` | No | Your personal example sentence |
| `translation` | No | English translation of sentence |
| `tags` | No | Comma-separated tags (e.g. N5,食) |

**Tip:** Leave `sentence` and `translation` blank for vocab you haven't used in a sentence yet. You can always edit the card in Anki later.

---

## Usage

Make sure **Anki Desktop is open**, then run:

```bash
# Preview what will be added (no changes made)
python add_cards.py vocab.csv --dry-run

# Add cards to default deck (Japanese::Kanji Vocab)
python add_cards.py vocab.csv

# Add to a custom deck
python add_cards.py vocab.csv --deck "Japanese::N5"
```

---

## Card Types Created

The script creates **3 cards per vocab word**:

| Card | Front | Back |
|---|---|---|
| Recognition | Kanji | Reading + Meaning + Sentence |
| Production | English meaning | Kanji + Reading + Sentence |
| Reading | Kanji (reading prompt) | Reading + Meaning |

---

## Workflow

1. Take notes during kanji video lesson (3 kanji, 5 words each)
2. Star the 2–3 words you want in Anki
3. Add starred words to `vocab.csv`
4. Run the script with Anki open
5. Cards appear in your deck immediately — ready for review

---

---

## parse_talkio.py — Import Talkio Corrections

Parses a Talkio session transcript and automatically extracts correction cards.

### What it extracts
Every place where Talkio shows:
```
User: <what you said>
Suggestion: <more natural version>
```
becomes one Anki card:
- **Front**: What you said
- **Back**: Natural version + pinpointed diff note (e.g. `✗ 店から買ってします → ✓ 店で買って飲みます`)

### Usage

```bash
# Preview without adding anything
python3 parse_talkio.py chat-7.txt --dry-run

# Add to Anki
python3 parse_talkio.py chat-7.txt

# Custom deck name and session tag
python3 parse_talkio.py chat-7.txt --deck "Japanese::Talkio Corrections" --tag "talkio-2026-05"
```

### After each Talkio session

1. Download transcript from Talkio (the `.txt` file)
2. Run dry-run to preview corrections
3. Run without `--dry-run` to add cards
4. Review new correction cards in Anki

---

## Deck Structure (Recommended)

```
Japanese
├── Kanji Vocab           ← add_cards.py
├── Talkio Corrections    ← parse_talkio.py
└── Grammar Patterns      ← future
```

---

## First-Time Setup (venv)

```bash
cd japanese-anki-automation
python3 -m venv venv
source venv/bin/activate      # Mac/Linux
pip install requests
```

On Windows:
```
venv\Scripts\activate
pip install requests
```
