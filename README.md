# HanyuBuTaiNan — Chinese Etymology & Story Guide — Local Folder Setup

This folder contains the offline-first study app (`hanyubutainan.html`) and its modular sibling data files. No build step, framework, or backend server is required.

## How to Run (`file://`)

1. Keep `hanyubutainan.html` and the sibling `data_*.js` files listed below in the **same directory** (or build a single-file bundle with `python3 bundle_release.py`).
2. Double-click `hanyubutainan.html` (or open its `file:///...` path directly in Chrome, Edge, Safari, or Firefox).
3. If your browser blocks `file://` `<iframe>` PDF embedding under a strict local sandbox, use the **Load PDF File** button inside the **Textbooks** tab to open a PDF directly from disk, or click **Open PDF in New Tab**.

## Core Data & Optional Sibling Files

| Filename | Purpose | Required? |
|---|---|---|
| `data_etymology.js` | Oracle-bone SVG evolution stages, 238 radicals, 660 character breakdowns, 27 deep stories & idioms | Core data module (degrades with notice if missing) |
| `data_vi.js` | Vietnamese glosses, localized story maps, and 4,225-character Hán Việt readings | Core data module (degrades with notice if missing) |
| `data_hsk.js` | Complete Holistic HSK vocabulary (11,470 rows across HSK 2.0 / 3.0 / 2026) and textbook page cross-references | Core data module (degrades with notice if missing) |
| `data_examples.js` | 9,370 example sentences with pinyin and translations (≥93% HSK 1–6 coverage) | Core data module (examples hidden if missing) |
| `data_textbooks.js` | Textbook companion guides for 3 courses / 48 lessons (lazy-loaded on demand when opening Textbooks) | Lazy-loaded on Textbooks tab |
| `cc_cedict_data.js` | Offline CC-CEDICT supplement (121,665 entries loaded via `<script src="cc_cedict_data.js">`) | Optional (core HSK search works without it) |
| `manifest.json`, `sw.js` | Optional PWA manifest & offline Service Worker (registered only over `https://` or `localhost`, skipped on `file://`) | Optional (hosted PWA only) |
| `bundle_release.py` | Optional script that inlines `data_*.js` into `hanyubutainan.standalone.html` for single-file sharing | Helper script |
| `test_hanyubutainan.py` | Static XSS lint + headless Chromium/Edge CDP regression suite (`python3 test_hanyubutainan.py`) | Test script |
| `hsk1_vi.pdf` | New HSK Course 1 PDF (148 pages, Chinese-Vietnamese scan) | Optional (for Textbooks PDF viewer) |
| `hsk2_en.pdf` | New HSK Course 2 PDF (164 pages, Chinese-English scan) | Optional (for Textbooks PDF viewer) |
| `hsk3_vi.pdf` | New HSK Course 3 PDF (212 pages, Chinese-Vietnamese scan) | Optional (for Textbooks PDF viewer) |

## Standardized PDF Filenames

The PDFs were standardized to plain ASCII filenames to avoid Unicode NFD/NFC mismatch, spaces, and CJK encoding issues across operating systems and browsers:

| Book | Original Filename | Standardized ASCII Filename |
|---|---|---|
| HSK 1 | `hsk1 - tiếng việt (3.0).pdf` | `hsk1_vi.pdf` |
| HSK 2 | `新HSK2 教材 @Nev_HSK_book.pdf` | `hsk2_en.pdf` |
| HSK 3 | `HSK3 - Tiếng Việt (3.0).pdf` | `hsk3_vi.pdf` |

## Attributions & Copyright Notes

- **Tatoeba Example Sentences (`data_examples.js`):** Selected Chinese-English sentence pairs sourced from [Tatoeba](https://tatoeba.org) under **CC-BY 2.0 FR**, combined with HSK/textbook examples and curated usage sentences.
- **CC-CEDICT (`cc_cedict_data.js`):** Community-maintained Chinese-English dictionary under CC-BY-SA.
- **Textbook PDFs:** Scans of published textbooks. Keeping them locally next to `hanyubutainan.html` is suitable for private personal study. If you share or host this app publicly, omit the PDFs and let users load their own copies via **Load PDF File**.
