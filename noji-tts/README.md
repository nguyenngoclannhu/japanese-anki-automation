# Noji TTS

Automates wrapping Japanese paragraphs in `<tts>` on [noji.io](https://noji.io) flashcards via Playwright. Runs trusted DOM events through Chrome DevTools Protocol, which synthetic in-page events couldn't.

## Setup (one time)

```bash
cd noji-tts
npm install
npx playwright install chromium
```

## Run

```bash
npm start
```

By default targets the deck `https://noji.io/deck/35476809`. Override with:

```bash
DECK_URL='https://noji.io/deck/<id>' npm start
```

### First run

A Chromium window opens. Sign in via Google, navigate to the deck so you see the cards view (with the "X/Y cards" counter and pencil), come back to the terminal, and press Enter. The script takes over from there.

### Subsequent runs

The script reuses the Chrome profile in `.chrome-profile/` so you stay logged in. It opens the deck URL directly and starts processing.

## Behavior

- Per card: open editor → wrap front Japanese (`p:nth-child(2)`) → wrap back Japanese (first `<p>` containing Japanese chars and no `× ✓ →` symbols) → save → click next-arrow → repeat to last card.
- **Idempotent.** Skips a side if its paragraph already contains `<tts>`. Safe to re-run; missed cards from a previous run are picked up automatically.
- Verifies `<tts>` appears after each click (4s timeout). Halts on first failure rather than corrupting subsequent cards.
- Starts from whatever card is currently shown — to do every card, navigate to card 1 in the open window first, then re-run.

## Why Playwright (and not a console script)

The first attempt was a JavaScript snippet pasted into the browser DevTools console. It could find every element (Edit button, TTS toolbar button, Save, Next, Japanese paragraphs) and select text correctly, but **synthetic mouse/pointer events were silently ignored** by the TTS button.

noji.io is built on **React Native Web** (recognizable from class names like `r-13awgt0 r-1loqt21 r-1otgn73`, and `<div tabindex="0">` wrappers around SVG icons). RNW's responder system checks `event.isTrusted` and rejects events dispatched programmatically from the page. Even with:

- Correct hit-testing via `document.elementFromPoint(x, y)`
- Real focus on the editor and a valid contenteditable selection
- `mousedown.preventDefault()` to preserve selection across the click
- Hovering the real mouse over the button before dispatching events

…nothing triggered the wrap. Synthetic events fundamentally cannot set `isTrusted: true`.

**Playwright bypasses this** because `page.click()` / `locator.click()` route through Chrome DevTools Protocol → `Input.dispatchMouseEvent` → events that the OS/browser stamps as trusted. The selectors that *found* elements in-page work fine inside `page.evaluateHandle`; only the *click delivery* needs CDP.

If you ever automate another site and find your console script silently does nothing despite correctly locating elements, check for the RNW signature and jump straight to Playwright.

## Selectors used (for future reference)

The DOM has no stable IDs/`data-*` attributes; everything is utility classes that change between renders. The script uses these stable signals:

- **Pencil (Edit) button:** 3rd small button (`30–60px square`) in the top bar (`top < 100`).
- **Save button:** `<div tabindex="0">` ancestor of `svg path[d^="M20.707 6.299"]` (the white check on blue circle).
- **Next arrow:** `<div tabindex="0">` ancestor of `svg path[d^="M7.293 3.293"]` whose left edge is in the right half of the viewport (left half is the previous arrow, same SVG flipped).
- **TTS button:** `<div tabindex="0">` containing `svg path[d^="m6.621 7.379"]` (speaker icon), constrained to the editor container.
- **Front Japanese paragraph:** `#RTE_front_side > div > p:nth-child(2)` — fixed by noji's card template.
- **Back Japanese paragraph:** first `<p>` under `#RTE_back_side > div` whose text contains Japanese characters (`぀-ゟ`, `゠-ヿ`, `一-鿿`) and no `× ✓ →` symbols (those are correction-line markers).

If noji ships a UI update and the script breaks, the path-prefix selectors (`d^=`) are the things most likely to need updating. The diagnostic technique we used: outline every `<div tabindex="0">` and label by index, then identify visually which is which (see git history for snippets).

## Known issues

- **Occasional back-side `<tts> wrap` timeout.** Race between clicking into the back paragraph and noji finishing its re-render after the front wrap. Mitigated by re-fetching the paragraph handle after the click (see `wrapSide` in `tts.js`). If it still fires occasionally, just re-run — idempotency handles it.

## Files

- `tts.js` — the script
- `package.json` — npm config (Playwright dependency)
- `package-lock.json` — pinned dependency tree
- `README.md` — this file
- `.chrome-profile/` — persisted Chrome user data (login cookies, etc.); **do not commit**
- `node_modules/` — npm packages; **do not commit**

## .gitignore

The repo root `.gitignore` already excludes:

```
noji-tts/node_modules/
noji-tts/.chrome-profile/
```
