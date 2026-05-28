import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';
import readline from 'readline';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const USER_DATA_DIR = path.join(__dirname, '.chrome-profile');
const DECK_URL = process.env.DECK_URL || 'https://noji.io/deck/35476809';
const SKIP_TIME = process.env.SKIP || 1;

function log(...a) { console.log('[TTS]', ...a); }
function prompt(q) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(res => rl.question(q, ans => { rl.close(); res(ans); }));
}

async function main() {
  log(`Launching Chromium with persistent profile at ${USER_DATA_DIR}`);
  const ctx = await chromium.launchPersistentContext(USER_DATA_DIR, {
    headless: false,
    viewport: { width: 1400, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  log(`Opening ${DECK_URL}`);
  await page.goto(DECK_URL, { waitUntil: 'domcontentloaded' });

  // Detect logged-in state by looking for the cards counter ("X/Y cards").
  const loggedIn = await page.locator('text=/\\d+\\s*\\/\\s*\\d+\\s*cards/').first().isVisible({ timeout: 8000 }).catch(() => false);
  if (!loggedIn) {
    log('Not logged in. Sign in via Google in the open window, navigate to the deck, then come back here.');
    await prompt('Press Enter once you see the deck cards view... ');
    await page.goto(DECK_URL, { waitUntil: 'domcontentloaded' });
    await page.locator('text=/\\d+\\s*\\/\\s*\\d+\\s*cards/').first().waitFor({ timeout: 30000 });
  }
  log('Deck ready.');

  // Helpers running inside the page context (trusted events come from page.click etc.)
  async function readProgress() {
    return page.evaluate(() => {
      const m = document.body.innerText.match(/(\d+)\s*\/\s*(\d+)\s*cards/i);
      return m ? { cur: +m[1], total: +m[2] } : null;
    });
  }

  async function pencilHandle() {
    return page.evaluateHandle(() => {
      const btns = [...document.querySelectorAll('div[tabindex="0"]')].filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 30 && r.width < 60 && r.height > 30 && r.height < 60 && r.top < 100 && el.querySelector('svg path');
      });
      return btns[2] || null;
    });
  }

  async function saveHandle() {
    return page.evaluateHandle(() => {
      const svg = document.querySelector('svg path[d^="M20.707 6.299"]');
      if (!svg) return null;
      let el = svg;
      while (el && el.getAttribute?.('tabindex') !== '0') el = el.parentElement;
      return el;
    });
  }

  async function nextHandle() {
    return page.evaluateHandle(() => {
      const arrows = [...document.querySelectorAll('svg path[d^="M7.293 3.293"]')];
      const cands = arrows.map(p => {
        let el = p;
        while (el && el.getAttribute?.('tabindex') !== '0') el = el.parentElement;
        return el;
      }).filter(Boolean);
      const center = innerWidth / 2;
      return cands.find(b => b.getBoundingClientRect().left > center) || null;
    });
  }

  async function ttsBtnHandle(rteId) {
    return page.evaluateHandle((id) => {
      const rte = document.querySelector('#' + id);
      if (!rte) return null;
      const editorContainer = rte.closest('div[class*="r-13awgt0"]')?.parentElement || rte.parentElement.parentElement;
      const all = [...editorContainer.querySelectorAll('div[tabindex="0"]')];
      return all.find(el => {
        const r = el.getBoundingClientRect();
        if (!(r.width > 20 && r.width < 60 && r.height > 20 && r.height < 60)) return false;
        return !!el.querySelector('svg path[d^="m6.621 7.379"]');
      }) || null;
    }, rteId);
  }

  async function jaParagraphHandle(side) {
    return page.evaluateHandle((side) => {
      if (side === 'front') {
        return document.querySelector('#RTE_front_side > div > p:nth-child(2)') || null;
      }
      const ps = [...document.querySelectorAll('#RTE_back_side > div > p')];
      return ps.find(p => {
        const t = p.innerText || '';
        const hasJa = /[぀-ゟ゠-ヿ一-鿿]/.test(t);
        const hasArrow = /[×✓→]/.test(t);
        return hasJa && !hasArrow;
      }) || null;
    }, side);
  }

  async function pHasTts(handle) {
    return page.evaluate(el => !!el && el.innerHTML.includes('<tts'), handle);
  }

  async function clickElementHandle(handle, label) {
    const elem = handle.asElement();
    if (!elem) throw new Error(`${label}: handle is null`);
    await elem.scrollIntoViewIfNeeded();
    await elem.click({ timeout: 10000 });
  }

  async function selectParagraphContents(pHandle) {
    await page.evaluate(p => {
      const range = document.createRange();
      range.selectNodeContents(p);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }, pHandle);
  }

  async function wrapSide(rteId, side) {
    const pHandle = await jaParagraphHandle(side);
    const hasP = !!pHandle.asElement();
    if (!hasP) {
      if (side === 'back') { log(`  ${side}: no JA paragraph, skip`); return; }
      throw new Error(`${side}: paragraph not found`);
    }
    if (await pHasTts(pHandle)) { log(`  ${side}: already wrapped, skip`); return; }

    // Place caret inside the paragraph via a real click, then re-fetch the
    // paragraph (noji can re-render after the click) and select its contents.
    const pElem = pHandle.asElement();
    await pElem.scrollIntoViewIfNeeded();
    await pElem.click({ timeout: 5000 });
    await page.waitForTimeout(200);

    const freshHandle = await jaParagraphHandle(side);
    if (!freshHandle.asElement()) throw new Error(`${side}: paragraph disappeared after click`);
    if (await pHasTts(freshHandle)) { log(`  ${side}: already wrapped (post-click), skip`); return; }
    await selectParagraphContents(freshHandle);
    await page.waitForTimeout(150);

    const ttsHandle = await ttsBtnHandle(rteId);
    if (!ttsHandle.asElement()) throw new Error(`${side}: TTS button not found`);
    await clickElementHandle(ttsHandle, `${side} TTS`);

    // Verify <tts> appears within 4s. Re-fetch each tick because noji may swap the node.
    const deadline = Date.now() + 4000;
    while (Date.now() < deadline) {
      const fresh = await jaParagraphHandle(side);
      if (await pHasTts(fresh)) { log(`  ${side}: wrapped ✓`); return; }
      await page.waitForTimeout(120);
    }
    throw new Error(`${side}: <tts> wrap not detected`);
  }

  async function processOneCard() {
    const pencil = await pencilHandle();
    if (!pencil.asElement()) throw new Error('Edit (pencil) not found');
    await clickElementHandle(pencil, 'Edit');

    await page.locator('#RTE_front_side').waitFor({ timeout: 6000 });
    await page.waitForTimeout(300);

    await wrapSide('RTE_front_side', 'front');
    await page.waitForTimeout(150);
    await wrapSide('RTE_back_side', 'back');
    await page.waitForTimeout(200);

    const save = await saveHandle();
    if (!save.asElement()) throw new Error('Save not found');
    await clickElementHandle(save, 'Save');

    await page.locator('#RTE_front_side').waitFor({ state: 'detached', timeout: 6000 });
    await page.waitForTimeout(400);
  }

  async function goNext(beforeCur) {
    const next = await nextHandle();
    if (!next.asElement()) throw new Error('Next arrow not found');
    await clickElementHandle(next, 'Next');
    const deadline = Date.now() + 6000;
    while (Date.now() < deadline) {
      const p = await readProgress();
      if (p && p.cur !== beforeCur) return;
      await page.waitForTimeout(150);
    }
    throw new Error('Card did not advance');
  }

  let processed = 0;
  while (true) {
    const prog = await readProgress();
    if (!prog) { log('Progress indicator missing, abort'); break; }
    log(`Card ${prog.cur}/${prog.total}`);
    try {
      await processOneCard();
      processed++;
    } catch (e) {
      console.error(`[TTS] FAILED on card ${prog.cur}:`, e.message);
      log('Stopped. Inspect the open window and re-run when ready.');
      break;
    }
    if (prog.cur >= prog.total) { log('Reached last card. Done.'); break; }
    try { for(let i = 0; i < SKIP_TIME; i++) { await goNext(prog.cur);} }
    catch (e) { console.error('[TTS] next failed:', e.message); break; }
  }

  log(`Done. Processed ${processed} card(s).`);
  log('Browser left open so you can verify. Close it manually or press Enter to quit.');
  await prompt('');
  await ctx.close();
}

main().catch(e => { console.error(e); process.exit(1); });
