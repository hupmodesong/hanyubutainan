# `hanyubutainan.html` — Bugs & Feature Improvements (Handoff)

> **Audience:** an AI coding agent (or developer) with no prior context.
> **Target file:** `hanyubutainan.html` (~2.2 MB, ~12.1k lines; one HTML file, inline CSS + one inline `<script>` starting at line ~2962).
> It is the renamed, newer build of the "Chinese Etymology & Story Guide" (HSK 1-9 study app).
> Line numbers refer to that file as reviewed and will shift after edits. Search by symbol/text instead.
> Everything below was verified by running the page in headless Chromium (Playwright) at 1280px and 375px width, plus static analysis of the inline JS (`node --check` passes).

---

## 1. App overview

Single self-contained HTML app (no framework, no build step) with optional sibling files:

| File | Purpose |
|---|---|
| `cc_cedict_data.js` | `window.CC_CEDICT_RAW = [[simp, trad, pinyin_with_tone_marks, meaning], ...]` (~125k rows, ~10 MB). Loaded by `<script src="cc_cedict_data.js">` (line ~2961). App works without it (shows a notice). |
| `hsk1_vi.pdf`, `hsk2_en.pdf`, `hsk3_vi.pdf` | Textbook scans shown in the Textbooks tab (`TEXTBOOK_DATA[].file`). |

**Tabs** (`[role=tab]`, `data-view`): `dictionary`, `vocab-list`, `hsk`, `lab`, `flashcards`, `textbooks`.

**Useful selectors:** `#dictSearchInput`, `#dictVocabResults`, `#dictDeepResults`, `#dictMatchCount`, `#dictEmptyOnlineBtn` ("Analyze & Add Online"), `#addWordInput`, `#exportJsonBtn`, `#exportCsvBtn`, `#importBackupBtn`, `input[type=file]`, `#statVocabList`, `#flashDeckSelect`, `#flashCounter`, `#flashFlipBtn`, `#langToggleBtn`, `#themeToggleBtn`.

**Persistence:** `localStorage` key `zh_etymology_app_v4`. Keys: `schemaVersion, theme, lang, scriptMode, speechRate, hskStandard, flashDeck, vocabListIds, mastered, customEntries, srs, studyStats ({streak,lastDate,todayCount,dailyGoal}), onlineCache, viCache`.

**Custom entry shape** (fields): `id, type, isCustom, isOnlineWikt, hsk, levels, hskNew, hskNewest, hskOld, simp, trad, pinyin, syllables, meaning, meaningVi, hanViet, categories, badges[{label,cls}], complexity, evoChars, structure, originalStory, whyItMeans, compTags, related, exampleZh, exampleAudio, pyNorm, pyCompact, meanCleanNorm, meanNorm, meanViNorm, _analyzed, tbRefs`.

## 2. Ground rules (don't break)

- Keep it **one HTML file** that works offline from `file://`. No frameworks, no new runtime network calls.
- Do not embed PDFs or the CEDICT data in the HTML.
- Keep the `localStorage` key; if the saved shape changes, bump `schemaVersion` and add a migration.
- Any string that comes from data, user input, imports, or the network must go through `escapeHtml()` before it reaches `innerHTML` (HTML text *and* attributes).
- New UI text needs EN + VI strings (follow existing i18n tables).

---

## 3. Bug (fix first)

### B1. Stored XSS: a shared backup file can run script on import — **HIGH**

**What happens.** `badges[].cls` of a custom entry is placed into a `class="..."` attribute **without escaping**, so a crafted backup JSON can break out of the attribute and run script. Anyone who imports a backup file from someone else is exposed.

**Where** (text to search: `class="badge ${b.cls}"`):
- vocab-list card renderer — line ~10309
- dictionary result card renderer — line ~10378
- inspector/modal renderer — line ~10898
- (A fourth renderer at ~11278 already does it right: `${escapeHtml(b.cls)}`.)
- Import normalization doesn't validate it: line ~8761, `rawCe.badges.filter((b) => b && b.label && b.cls)`.

**How it was verified.** Payload `x"><img src=x onerror=window.__xss=1>` injected into **every** string field of a custom entry, then rendered in the vocab tab, dictionary search, modal and flashcards: **only `badges[].cls` executed**. Then an exported backup was edited (`badges[0].cls` = payload, `vocabListIds` containing the entry id) and imported via the normal import button → script ran (`window.__xss === 1`, injected `<img>` in the DOM).

**Required fix (both layers).**
1. Escape at the three unsafe render sites: `<span class="badge ${escapeHtml(b.cls)}">`.
2. Allow-list on import: keep a badge only if `/^[\w-]+$/.test(String(b.cls))` (and `label` is a string). Prefer a single `sanitizeImportedEntry(entry)` that also type-checks every field used in templates (strings are strings, arrays are arrays, numbers are numbers, strips unknown keys), so future fields can't reintroduce the bug.
3. Optional: add a tiny tagged-template helper (e.g. `html\`...\``) that escapes interpolations by default and use it for new code.

**Acceptance.**
- Importing the backup described above leaves `window.__xss` undefined and injects no `<img src=x>`.
- Repeat the all-fields injection test (§6.2): zero fields execute in any view.
- Valid exports still round-trip (JSON and CSV) with badges rendering normally.

---

## 4. Feature improvements

### F1. Real example sentences (content gap) — Priority 1
Only **337** entries in `HSK_EXAMPLES` have a real sentence, out of ~11,554 words (~3%). For the rest, the card's "Example" box just repeats the headword and gloss.
- Add sentences from a freely licensed source (e.g. Tatoeba, CC-BY — keep attribution) or reviewed generated sentences, ideally at the word's HSK level, with pinyin and EN/VI translation. Store them in a separate data file (see C1), not inline.
- If a word has no real example, **hide** the Example box instead of repeating the headword.
- **Acceptance:** ≥ 90% of HSK 1-6 entries have an example; no card shows the headword as its own example.

### F2. Make the daily goal configurable — Priority 1
`studyStats.dailyGoal` is hard-coded to 20 ("Today: 1 / 20") and there's no UI to change it.
- Add a small control (e.g. in the flashcards header or a settings popover) with presets (10 / 20 / 50 / custom), saved in `studyStats.dailyGoal`, EN + VI labels.
- **Acceptance:** changing the goal updates the "Today: n / goal" chip immediately and survives reload and export/import.

### F3. Separate "New" and "Due" counts — Priority 2
The "Due" chip / "Due Now" deck includes never-studied cards (60 on a fresh profile, 59 after one review). Show **Due** (previously reviewed and now due) and **New** (never seen, capped per day) separately, Anki-style, and add a "new cards per day" limit.
- **Acceptance:** fresh profile shows Due 0, New 60 (or the limit); after reviewing one card, that card leaves New and appears in Due when its interval elapses.

### F4. Speech (TTS) robustness — Priority 2
Speech uses `speechSynthesis` only. The code calls `getVoices()` but has **no `voiceschanged` listener**; in Chrome the voice list loads asynchronously, so the first tap can return an empty list and use the wrong (non-Chinese) default voice. Some devices have no Chinese voice at all.
- Add a `voiceschanged` listener and re-pick a `zh-CN` voice when the list arrives; remember the chosen voice.
- If no Chinese voice exists, show a short hint ("No Chinese voice installed on this device…") instead of silently speaking with the wrong voice.
- **Acceptance:** first tap after page load uses a `zh-*` voice when one exists; the hint shows when none does.

### F5. Tone colors — Priority 3
No tone coloring exists. Add an optional toggle (persisted) that colors pinyin and/or hanzi by tone (1-4 + neutral), with a color-blind-safe palette that works in light and dark mode, plus a small legend.

### F6. Typing / dictation practice — Priority 3
No pinyin-typing or dictation drill was found. Add a flashcard mode: show the meaning (or play audio) → user types pinyin (tone numbers or marks accepted) or the hanzi; mark correct/incorrect and feed the result into the SRS grades.

### F7. Backup safety & storage — Priority 2
All user data lives in one `localStorage` object, including `onlineCache` and `viCache`, which can grow without bound and could eventually hit the ~5 MB quota.
- Cap/evict the caches (e.g. LRU, max N entries) or move them to IndexedDB.
- Show a "Last backup: …" note and a gentle reminder to export after N days or N reviews.
- If `localStorage.setItem` fails, show a toast (don't fail silently).
- **Acceptance:** adding thousands of cached lookups never throws; the user is told if saving fails.

### F8. Optional: installable/offline PWA — Priority 3
No service worker. If the app is ever hosted: add a manifest + service worker caching the HTML and `cc_cedict_data.js`. (Keep `file://` usage working.)

---

## 5. Code-health improvements

### C1. Move embedded data out of the inline script — Priority 1 (maintainability)
About **84%** of the inline script (~1.5 MB of 1.85 MB) is data constants: `HSK_COMPLETE_RAW` (~920 KB), `TEXTBOOK_DATA` (~236 KB), `EXTRA_CHAR_DATA` (~92 KB), `STORY_ENTRIES` (~86 KB), `SCRIPT_EVOLUTION` (~44 KB), `HAN_VIET_DICT` (~43 KB), `VI_STORY_MAP` (~35 KB), `HSK_EXAMPLES` (~27 KB).
- Move them to sibling `*.js` data files (same pattern as `cc_cedict_data.js`, each with a missing-file notice), and lazy-load `TEXTBOOK_DATA` only when the Textbooks tab opens.
- Optionally add a small script that inlines everything into one HTML for release.
- **Acceptance:** `index.html` shrinks to a few hundred KB; every tab works with all data files present; missing optional files produce a visible notice, not an exception.

### C2. Structure and conventions — Priority 2
112 top-level functions and ~137 `getElementById` calls share one scope. Group code into clearly separated sections (state, storage, i18n, search, renderers per tab, flashcards/SRS, textbooks), cache element lookups, and document the "escape before innerHTML" rule at the top of the script. (A lint-style check — grep for `${` inside `innerHTML` templates without `escapeHtml` — would have caught B1.)

### C3. Keep an automated browser test script — Priority 2
Commit the Playwright checks used in this review (§6) so regressions are caught.

### C4. Minor accessibility — Priority 3
At 375px, ~90 interactive elements on the HSK tab are still under 32px tall/wide (tag chips, Speak/Add/Master). Make touch targets ≥ 40px on `max-width: 640px`.

---

## 6. How to test

Use headless Chromium via Playwright, opening the HTML from `file://` in a folder that contains it (and optionally `cc_cedict_data.js`). Listen for `pageerror` and `console` errors.

```python
from playwright.sync_api import sync_playwright
URL = 'file:///path/to/index.html'
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1280, 'height': 900})
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(1000)
    pg.fill('#dictSearchInput', 'love'); pg.wait_for_timeout(400)
    print(pg.inner_text('#dictMatchCount'), errs)
```

Mobile: `b.new_context(viewport={'width':375,'height':740}, is_mobile=True, has_touch=True)`.

### 6.1 Test data for `cc_cedict_data.js` (real file not provided)
Generate from CC-CEDICT `cedict_ts.u8` (`傳統 传统 [chuan2 tong3] /tradition/`): `window.CC_CEDICT_RAW=[[simp, trad, "chuán tǒng", "tradition"], …];` — pinyin with tone marks (mark on `a`/`e`, else `o` of `ou`, else last vowel; `u:`→`ü`; tone 5 no mark), definitions joined with `; `.

### 6.2 XSS regression test (B1)
1. Open the app **without** `cc_cedict_data.js`. Search `蓝莓酸奶` → click "Analyze & Add Online" (builds a custom entry offline).
2. Click "Export JSON Backup" and save the file.
3. Edit the JSON: set `customEntries[0].badges[0].cls` to `x"><img src=x onerror=window.__xss=1>` and set `vocabListIds` to `[customEntries[0].id]`.
4. In a fresh browser context, import the file via `input[type=file]` on the Vocab List tab.
5. **Pass** = `window.__xss` is undefined and `document.querySelectorAll('img[src=x]').length === 0` in vocab tab, dictionary search, modal and flashcards.
6. Also loop over every string field of the entry (except `id`, `simp`, `type`) appending the payload; none may execute in any view.

---

## 7. Already fixed in this build — don't regress

| Area | Check |
|---|---|
| Missing files | No `cc_cedict_data.js` → notice "Extended dictionary (cc_cedict_data.js) not found. Core HSK entries still work."; no PDFs → viewer shows "Expected file: hsk1_vi.pdf" and a hint to use "Load PDF File" |
| Textbooks UI | Prev/Next Page, Open PDF, Load PDF File and Practice Lesson Flashcards are styled; all 48 lessons render; "Add N Lesson Words" doesn't duplicate; page input clamps |
| Search ranking | `love` → 爱 first; `hello` → 你好 first; `a` → ~4 matches; `百/包/班` → hundred / bag / class |
| Hán Việt | 4,225-character dictionary; compounds labeled "Per-character readings" |
| Card text | `越来越` shows "越 ×2 … 来: to come", no "char" placeholder, no duplicated story sentence |
| Flashcards | Opens on "Due Now" (60 cards); grades Again <10m / Hard 12h / Good 1d / Easy 4d; "Today / Streak / Due" chips update |
| Mobile | No horizontal overflow at 375px; sticky tab bar; ~11px gap above HSK search box |
| Import validation | Backup with invalid entries → "Import aborted: 0 valid entries (N invalid skipped)", nothing half-imported |
| Accessibility | All inputs labeled; skip link; `aria-pressed` on toggles; `prefers-reduced-motion` respected |
| Misc | No console errors on load; modal focus trap + Escape; dark mode incl. OS preference; JSON/CSV export→import round trip |

## 8. Definition of done

- [ ] **B1** fixed and the §6.2 test passes (this is the only must-fix security item).
- [ ] F1 and F2 implemented (or a note explaining why not); F3-F8 and C1-C4 attempted in the listed priority order.
- [ ] §7 regression table still passes; zero unexpected console errors.
- [ ] Short change log (what changed, by symbol name) and any items you could not verify (e.g. real PDF rendering).
