# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

English- and Vietnamese-speaking learners of Mandarin Chinese (HSK 1 through HSK 7–9) who want to understand *why* characters and words mean what they mean through verifiable etymology, radical composition, phonetic sound families, spaced repetition flashcards, and official HSK textbooks.

## Product Purpose

Chinese Etymology & Story Guide (汉语不太难 / HanyuBuTaiNan) replaces rote character memorization with structural and historical comprehension. It unites an offline-first HSK 1–9 + CC-CEDICT dictionary, curated character origin narratives, an interactive Radical & Six Writings (六书) Lab, an SM-2 Spaced Repetition flashcard studio, and a bilingual (EN/VI) Official Textbook companion.

## Positioning

A zero-dependency, offline-capable single-page lexicographic studio that links every HSK 1–9 word directly to its semantic radicals, phonetic series, oracle-bone-to-regular script evolution, scholarly confidence ratings, and level-calibrated example sentences in both English and Vietnamese.

## Operating Context

Used daily on desktop, half-screen split windows (700–960px alongside notes or PDFs), tablets, and mobile browsers. Must function 100% offline from `file://` or static hosting (`hanyubutainan.html` and `hanyubutainan.standalone.html`) with local progress persisted in `localStorage` and exportable to JSON, Anki CSV, and Excel (`.xlsx`).

## Capabilities and Constraints

- Six integrated study surfaces: Dictionary & Search, My Vocab List, Holistic HSK (1–9 across 2.0, 3.0, and 2026 Revised standards), Radical Lab & Six Writings, Flashcards (Flip, Type Pinyin, Definition, Dictation), and Official Textbooks (HSK 1–3 PDF + bilingual guide).
- `hanyubutainan.html` must remain a lean (<500 KB) self-contained application shell loading `data_etymology.js`, `data_vi.js`, `data_hsk.js`, `data_examples.js`, `data_textbooks.js`, and optional `cc_cedict_data.js` / `rust_core.js`.
- Flashcard Pinyin verification must be completely tone-format agnostic (accepting tone marks, tone numbers 1–5, or toneless Pinyin).
- All filter controls and HSK Level boxes must fit cleanly and truncate with ellipsis at half-screen widths (700–960px).

## Product Principles

1. **Verifiable Scholarship over Folk Mnemonics**: Every etymology entry states its paleographic confidence level and primary source (*Shuowen Jiezi*, oracle bone inscriptions, Wiktionary glyph analysis).
2. **Split-Screen & Half-Window Ergonomics**: Learners routinely study with the browser snapped to half the screen; controls and HSK level pickers must never overflow or break layout at 700–960px.
3. **Frictionless Input Forgiveness**: Pinyin practice tests phoneme recall without penalizing input method differences between tone marks, tone numbers, or toneless typing.
4. **Offline Durability**: Every feature works without a backend server, with full backup portability via JSON, CSV, and native `.xlsx` generation.
