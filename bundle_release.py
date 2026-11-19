#!/usr/bin/env python3
"""Optional release bundler: inlines core data_*.js modules into a standalone HTML build.
Keeps cc_cedict_data.js and PDFs external as required."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
SRC_HTML = ROOT / "hanyubutainan.html"
OUT_HTML = ROOT / "hanyubutainan.standalone.html"

INLINE_SCRIPTS = [
    "data_etymology.js",
    "data_vi.js",
    "data_hsk.js",
    "data_examples.js",
    "data_textbooks.js",
    "rust_core.js",
]

html = SRC_HTML.read_text(encoding="utf-8")
for name in INLINE_SCRIPTS:
    js_path = ROOT / name
    if not js_path.exists():
        raise FileNotFoundError(f"Missing required data file: {js_path}")
    payload = js_path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    tag_re = re.compile(rf'<script\s+src="{re.escape(name)}"\s*></script>')
    if tag_re.search(html):
        html = tag_re.sub(lambda _m: f"<script>\n{payload}\n</script>", html, count=1)
    elif name == "data_textbooks.js":
        # Inject lazy textbook data inline before the main app script if referenced lazily
        html = html.replace(
            '<script src="cc_cedict_data.js"></script>',
            f'<script src="cc_cedict_data.js"></script>\n  <script>\n{payload}\n</script>',
            1,
        )

OUT_HTML.write_text(html, encoding="utf-8")
print(f"Wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.1f} KB)")
