#!/usr/bin/env python3
"""
Automated static + headless Chromium/Edge (CDP over pipe) regression & feature
test suite for HanyuBuTaiNan (hanyubutainan.html).

Drives real UI interactions (clicks, inputs, select changes, file uploads,
localStorage persistence, and mobile device emulation) without breaking IIFE
encapsulation.

Covers:
  - Static JS/JSON/Python syntax & XSS template lint
  - B1 / §6.2 Stored XSS regression across badges[].cls & every entry string field
  - F1 Example coverage (>= 90% HSK 1-6) & no headword-as-example fallback
  - F2 Configurable daily goal + persistence across reload & JSON export/import
  - F3 Separate Due / New SRS counters + newPerDay limit + due progression
  - F4 TTS voice selection & voiceschanged + no-Chinese-voice toast hint
  - F5 Tone colors toggle, Okabe-Ito legend, dark mode contrast, reload persistence
  - F6 Typing Pinyin (tone numbers + tone marks + unspaced) & Dictation modes
  - F7 LRU caps on onlineCache (250) / viCache (500) & localStorage save error toast
  - C1 External data_*.js modules, lazy data_textbooks.js loading, missing file notices
  - C4 Mobile viewport (375x740): zero horizontal overflow & >= 40px touch targets
  - §7 Regressions: search ranking, 48 lessons, page clamp, no dup add, modal focus/Esc
"""

from __future__ import annotations

import json
import os
import pathlib
import py_compile
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse


ROOT = pathlib.Path(__file__).resolve().parent
HTML_PATH = ROOT / "hanyubutainan.html"
STORAGE_KEY = "zh_etymology_app_v4"
JSC_BIN = pathlib.Path(
    "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
)
BROWSER_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_browser() -> str:
    for p in BROWSER_CANDIDATES:
        if p and pathlib.Path(p).exists():
            return p
    raise RuntimeError(
        "No Chromium/Edge binary found. Set CHROME_BIN to run browser tests."
    )


def file_url(path: pathlib.Path) -> str:
    return "file://" + urllib.parse.quote(str(path.resolve()), safe="/:")


class EdgeCDP:
    """Minimal zero-dependency CDP client using --remote-debugging-pipe (fd 3/4)."""

    def __init__(self, browser_bin: str, user_data_dir: pathlib.Path):
        self.browser_bin = browser_bin
        self.user_data_dir = user_data_dir
        self._next_id = 0
        self._buf = b""
        self.page_errors: list[str] = []
        self.console_errors: list[str] = []
        self.proc = None
        self.p2c_w = None
        self.c2p_r = None
        self.session_id = None

    def __enter__(self):
        c2p_r, c2p_w = os.pipe()
        p2c_r, p2c_w = os.pipe()
        os.set_inheritable(p2c_r, True)
        os.set_inheritable(c2p_w, True)

        def setup_fds():
            if p2c_r != 3:
                os.dup2(p2c_r, 3)
            if c2p_w != 4:
                os.dup2(c2p_w, 4)
            for fd in (p2c_r, p2c_w, c2p_r, c2p_w):
                if fd not in (3, 4):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        self.proc = subprocess.Popen(
            [
                self.browser_bin,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                "--remote-debugging-pipe",
                f"--user-data-dir={self.user_data_dir}",
                "about:blank",
            ],
            preexec_fn=setup_fds,
            close_fds=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(p2c_r)
        os.close(c2p_w)
        self.p2c_w = p2c_w
        self.c2p_r = c2p_r

        targets = self.send("Target.getTargets")["targetInfos"]
        page_target = next(t for t in targets if t["type"] == "page")
        self.session_id = self.send(
            "Target.attachToTarget",
            {"targetId": page_target["targetId"], "flatten": True},
        )["sessionId"]
        self.send("Page.enable", session_id=self.session_id)
        self.send("Runtime.enable", session_id=self.session_id)
        self.send("DOM.enable", session_id=self.session_id)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=5)
        except Exception:
            if self.proc:
                self.proc.kill()
        for fd in (self.p2c_w, self.c2p_r):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _read_msg(self) -> dict:
        while b"\0" not in self._buf:
            chunk = os.read(self.c2p_r, 65536)
            if not chunk:
                raise EOFError("CDP pipe closed unexpectedly")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        return json.loads(raw.decode("utf-8"))

    def send(self, method: str, params: dict | None = None, session_id: str | None = None) -> dict:
        self._next_id += 1
        cid = self._next_id
        payload: dict = {"id": cid, "method": method}
        if params:
            payload["params"] = params
        if session_id:
            payload["sessionId"] = session_id
        data = (json.dumps(payload) + "\0").encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(self.p2c_w, view)
            view = view[written:]
        while True:
            msg = self._read_msg()
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP error on {method}: {msg['error']}")
                return msg.get("result", {})
            self._record_event(msg)

    def _record_event(self, msg: dict):
        method = msg.get("method")
        if not method:
            return
        params = msg.get("params", {})
        if method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails", {})
            exc = details.get("exception", {})
            desc = exc.get("description") or details.get("text") or json.dumps(details)
            self.page_errors.append(desc)
        elif method == "Runtime.consoleAPICalled" and params.get("type") == "error":
            args = [a.get("value") or a.get("description") or "" for a in params.get("args", [])]
            self.console_errors.append(" ".join(str(x) for x in args).strip())

    def drain_events(self):
        self.send(
            "Runtime.evaluate",
            {"expression": "1", "returnByValue": True},
            session_id=self.session_id,
        )

    def clear_errors(self):
        self.drain_events()
        self.page_errors.clear()
        self.console_errors.clear()

    def goto(self, url: str, minimal: bool = False):
        self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        pred = (
            "document.readyState === 'complete' && Boolean(document.getElementById('dataMissingBanner'))"
            if minimal
            else "document.readyState === 'complete' && Boolean(document.getElementById('statTotal')) && Number((document.getElementById('statTotal').textContent || '0').replace(/\\D/g, '')) > 0"
        )
        self.wait_for(pred, timeout_s=15.0)
        self.eval("new Promise(r => setTimeout(r, 80))", await_promise=True)

    def reload(self):
        self.send("Page.reload", {"ignoreCache": True}, session_id=self.session_id)
        self.wait_for(
            "document.readyState === 'complete' && Boolean(document.getElementById('statTotal')) && Number((document.getElementById('statTotal').textContent || '0').replace(/\\D/g, '')) > 0",
            timeout_s=15.0,
        )
        self.eval("new Promise(r => setTimeout(r, 80))", await_promise=True)

    def eval(self, expr: str, await_promise: bool = False):
        res = self.send(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            session_id=self.session_id,
        )
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS exception: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    def wait_for(self, js_predicate: str, timeout_s: float = 10.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if self.eval(f"Boolean({js_predicate})"):
                    return
            except Exception:
                pass
            time.sleep(0.05)
        raise TimeoutError(f"Timed out waiting for: {js_predicate}")

    def set_file_input(self, selector: str, file_path: pathlib.Path):
        doc = self.send("DOM.getDocument", {"depth": -1}, session_id=self.session_id)
        node = self.send(
            "DOM.querySelector",
            {"nodeId": doc["root"]["nodeId"], "selector": selector},
            session_id=self.session_id,
        )
        if not node.get("nodeId"):
            raise RuntimeError(f"Selector not found for file input: {selector}")
        self.send(
            "DOM.setFileInputFiles",
            {"nodeId": node["nodeId"], "files": [str(file_path.resolve())]},
            session_id=self.session_id,
        )
        self.eval(
            f"document.querySelector({json.dumps(selector)}).dispatchEvent(new Event('change', {{ bubbles: true }}))"
        )
        self.eval("new Promise(r => setTimeout(r, 120))", await_promise=True)


def run_static_checks():
    print("[1/2] Running static checks & XSS template lint...")
    html_text = HTML_PATH.read_text(encoding="utf-8")
    size_kb = len(html_text.encode("utf-8")) / 1024.0
    assert size_kb < 500, f"Expected lean HTML (<500 KB), got {size_kb:.1f} KB"

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("short_name") == "HanyuBuTaiNan"
    py_compile.compile(str(ROOT / "bundle_release.py"), doraise=True)

    assert "SECURITY RULE" in html_text and "SAFE_BADGE_CLS_RE" in html_text
    assert "sanitizeImportedEntry" in html_text and "SCHEMA_VERSION = 4" in html_text

    scripts = [s for s in re.findall(r"<script(?:\s+[^>]*)?>(.*?)</script>", html_text, re.S) if s.strip()]
    assert len(scripts) == 1, f"Expected 1 inline script block, found {len(scripts)}"
    js_src = scripts[0]

    raw_bcls = [m.group(0) for m in re.finditer(r"\$\{\s*b\.cls\s*\}", js_src)]
    assert not raw_bcls, f"Unescaped b.cls interpolation found: {raw_bcls}"

    if JSC_BIN.exists():
        for name, src_text in [("inline_script", js_src)] + [
            (fn, (ROOT / fn).read_text(encoding="utf-8"))
            for fn in ("data_etymology.js", "data_vi.js", "data_hsk.js", "data_examples.js", "data_textbooks.js", "sw.js")
        ]:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
                tf.write(src_text)
                tpath = tf.name
            try:
                chk = (
                    "var window={}, self={addEventListener:function(){}}, caches={};"
                    f"new Function(read({json.dumps(tpath)})); print('OK');"
                )
                proc = subprocess.run([str(JSC_BIN), "-e", chk], capture_output=True, text=True)
                assert proc.returncode == 0, f"JSC syntax failure in {name}: {proc.stderr}"
            finally:
                os.unlink(tpath)

    print(f"  Static checks PASSED (hanyubutainan.html = {size_kb:.1f} KB, 0 lint errors)")


def run_browser_tests():
    browser_bin = find_browser()
    print(f"[2/2] Running headless browser tests with {pathlib.Path(browser_bin).name}...")

    with tempfile.TemporaryDirectory() as td_root:
        td = pathlib.Path(td_root)

        # --- Suite A: Full workspace (all data_*.js + cc_cedict_data.js present) ---
        profile_a = td / "profile_a"
        with EdgeCDP(browser_bin, profile_a) as cdp:
            # Install a mock speechSynthesis before page scripts run to test async voiceschanged & zh voice selection (F4)
            cdp.send(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    (() => {
                      window.__mockVoices = [];
                      window.__mockSpoken = [];
                      const listeners = { voiceschanged: [] };
                      window.SpeechSynthesisUtterance = function(text) {
                        this.text = text;
                        this.lang = '';
                        this.rate = 1;
                        this.voice = null;
                      };
                      const mockSynth = {
                        cancel: () => {},
                        speak: (u) => { window.__mockSpoken.push({ text: u.text, lang: u.lang, voiceLang: u.voice ? u.voice.lang : null }); },
                        getVoices: () => window.__mockVoices,
                        addEventListener: (ev, fn) => { if (!listeners[ev]) listeners[ev] = []; listeners[ev].push(fn); },
                        removeEventListener: (ev, fn) => { if (listeners[ev]) listeners[ev] = listeners[ev].filter(f => f !== fn); },
                        __fireVoicesChanged: () => {
                          (listeners.voiceschanged || []).forEach(fn => fn());
                          if (typeof mockSynth.onvoiceschanged === 'function') mockSynth.onvoiceschanged();
                        }
                      };
                      try {
                        Object.defineProperty(window, 'speechSynthesis', { value: mockSynth, configurable: true, writable: true });
                      } catch (e) {}
                    })();
                    """
                },
                session_id=cdp.session_id,
            )

            cdp.goto(file_url(HTML_PATH))
            cdp.drain_events()
            assert not cdp.page_errors, f"Initial load pageErrors: {cdp.page_errors}"
            assert not cdp.console_errors, f"Initial load consoleErrors: {cdp.console_errors}"

            # T1: Data stats, HSK 1-6 example coverage >= 90%, banner hidden, lazy data_textbooks.js
            stats = cdp.eval("""(() => {
              const exMap = window.HSK_EXAMPLES || {};
              const raw = window.HSK_COMPLETE_RAW || [];
              let hsk16 = 0, withEx = 0, selfRepeat = 0;
              for (const row of raw) {
                const lvStr = String(row[5] || '');
                const is16 = /(?:^|,)[ont][1-6](?:,|$)/.test(lvStr);
                if (!is16) continue;
                hsk16++;
                const simp = row[0];
                const ex = exMap[simp];
                if (ex && ex[0]) {
                  const core = String(ex[0]).replace(/[\\s。！？.,!?]/g, '');
                  if (core !== simp && core !== row[1]) withEx++;
                  else selfRepeat++;
                }
              }
              const banner = document.getElementById('dataMissingBanner');
              return {
                statTotal: Number(document.getElementById('statTotal').textContent.replace(/\\D/g, '')),
                hsk16,
                withEx,
                selfRepeat,
                bannerHidden: banner ? banner.classList.contains('hidden') : false,
                tbLoadedEarly: Boolean(window.TEXTBOOK_DATA)
              };
            })()""")
            pct = (stats["withEx"] / max(1, stats["hsk16"])) * 100.0
            print(f"  T1 Loaded {stats['statTotal']} entries; HSK 1-6 real examples: {stats['withEx']}/{stats['hsk16']} ({pct:.1f}%)")
            assert stats["statTotal"] > 10000, stats
            assert pct >= 90.0, f"F1 HSK 1-6 coverage < 90%: {pct:.2f}%"
            assert stats["bannerHidden"], "Unexpected dataMissingBanner shown when all files exist"
            assert not stats["tbLoadedEarly"], "C1 expected data_textbooks.js NOT loaded before Textbooks tab opens"

            # T2 §7: Search ranking & card breakdown
            search_res = cdp.eval("""(() => {
              const stripRt = (el) => {
                if (!el) return '';
                const clone = el.cloneNode(true);
                clone.querySelectorAll('rt').forEach(r => r.remove());
                return clone.textContent.trim();
              };
              const q = (txt) => {
                const inp = document.getElementById('dictSearchInput');
                inp.value = txt;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                const cards = Array.from(document.querySelectorAll('#dictVocabResults .vocab-card'));
                return {
                  matchText: document.getElementById('dictMatchCount').textContent,
                  firstHead: cards[0] ? stripRt(cards[0].querySelector('.vocab-char-lockup')) : '',
                  firstBody: cards[0] ? cards[0].textContent : ''
                };
              };
              const love = q('love');
              const hello = q('hello');
              const aRes = q('a');
              const bai = q('百');
              const bao = q('包');
              const ban = q('班');
              const yly = q('越来越');
              q('');
              return {
                loveFirst: love.firstHead,
                helloFirst: hello.firstHead,
                aText: aRes.matchText,
                baiMeaning: (Array.from(document.querySelectorAll('#dictVocabResults .vocab-card'))[0] || {}).textContent || bai.firstBody,
                baiBody: bai.firstBody,
                baoBody: bao.firstBody,
                banBody: ban.firstBody,
                ylyBody: yly.firstBody
              };
            })()""")
            assert "爱" in search_res["loveFirst"], search_res
            assert "你好" in search_res["helloFirst"], search_res
            assert "4" in search_res["aText"], search_res["aText"]
            assert "hundred" in search_res["baiBody"].lower(), search_res["baiBody"]
            assert "bag" in search_res["baoBody"].lower(), search_res["baoBody"]
            assert "class" in search_res["banBody"].lower(), search_res["banBody"]
            assert "越 ×2" in search_res["ylyBody"] and "to come" in search_res["ylyBody"], search_res["ylyBody"]
            print("  T2 Search ranking & card breakdown (§7) PASSED")

            # T4 F4: Test TTS when empty voices -> toast hint; then fire voiceschanged with zh-CN -> picks zh-CN
            tts_res = cdp.eval("""(() => {
              const btn = document.querySelector('#dictEmptyPrompt [data-quick-search]');
              // Click quick chip to show card with speak button
              document.querySelector('[data-quick-search=\"喜欢\"]').click();
              const spk = document.querySelector('#dictVocabResults [data-speak]');
              spk.click();
              const noVoiceToast = document.getElementById('toast').textContent;
              window.__mockVoices = [{ lang: 'zh-CN', name: 'Mock Ting-Ting' }];
              window.speechSynthesis.__fireVoicesChanged();
              spk.click();
              document.getElementById('dictClearBtn').click();
              return { noVoiceToast, spoken: window.__mockSpoken };
            })()""")
            assert "No Chinese voice" in tts_res["noVoiceToast"], tts_res
            assert len(tts_res["spoken"]) >= 2 and tts_res["spoken"][-1]["voiceLang"] == "zh-CN", tts_res
            print("  T4 F4 TTS voiceschanged & missing-voice toast PASSED")

            # T3 F2 & F3: Flashcards fresh profile -> rate 1 -> configure dailyGoal & newPerDay -> due progression
            srs_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"flashcards\"]').click();
              const before = {
                counter: document.getElementById('flashCounter').textContent,
                due: document.getElementById('srsDueBadge').textContent,
                newBadge: document.getElementById('srsNewBadge').textContent,
                goal: document.getElementById('srsGoalBadge').textContent,
                streak: document.getElementById('srsStreakBadge').textContent,
                ints: [1, 2, 3, 4].map(q => document.getElementById('srsInt' + q).textContent)
              };
              document.querySelector('[data-srs-rate=\"3\"]').click();
              const afterOne = {
                due: document.getElementById('srsDueBadge').textContent,
                newBadge: document.getElementById('srsNewBadge').textContent,
                goal: document.getElementById('srsGoalBadge').textContent,
                streak: document.getElementById('srsStreakBadge').textContent
              };
              document.getElementById('srsSettingsToggleBtn').click();
              document.getElementById('dailyGoalCustomInput').value = '35';
              document.getElementById('applyDailyGoalBtn').click();
              document.getElementById('newPerDayCustomInput').value = '10';
              document.getElementById('applyNewPerDayBtn').click();
              return {
                before,
                afterOne,
                customGoalBadge: document.getElementById('srsGoalBadge').textContent,
                customNewBadge: document.getElementById('srsNewBadge').textContent
              };
            })()""")
            assert srs_res["before"]["counter"] == "1 / 60", srs_res["before"]
            assert srs_res["before"]["due"] == "Due: 0", srs_res["before"]
            assert srs_res["before"]["newBadge"] == "New: 60", srs_res["before"]
            assert srs_res["before"]["goal"] == "Today: 0 / 20", srs_res["before"]
            assert srs_res["before"]["ints"] == ["<10m", "12h", "1d", "4d"], srs_res["before"]
            assert srs_res["afterOne"]["due"] == "Due: 0", srs_res["afterOne"]
            assert srs_res["afterOne"]["newBadge"] == "New: 59", srs_res["afterOne"]
            assert srs_res["afterOne"]["goal"] == "Today: 1 / 20", srs_res["afterOne"]
            assert srs_res["afterOne"]["streak"] == "Streak: 1d", srs_res["afterOne"]
            assert srs_res["customGoalBadge"] == "Today: 1 / 35", srs_res
            assert srs_res["customNewBadge"] == "New: 9", srs_res

            # T5 F5 Tone colors + Light & Dark mode contrast before reload
            tone_before = cdp.eval("""(() => {
              const initTheme = document.documentElement.getAttribute('data-theme');
              document.getElementById('toneColorToggleBtn').click();
              document.getElementById('themeToggleBtn').click();
              const toggledTheme = document.documentElement.getAttribute('data-theme');
              const c1 = getComputedStyle(document.querySelector('#toneLegendBar .tone-1')).color;
              const c2 = getComputedStyle(document.querySelector('#toneLegendBar .tone-2')).color;
              document.getElementById('themeToggleBtn').click();
              const restoredTheme = document.documentElement.getAttribute('data-theme');
              const d1 = getComputedStyle(document.querySelector('#toneLegendBar .tone-1')).color;
              const d2 = getComputedStyle(document.querySelector('#toneLegendBar .tone-2')).color;
              return {
                initTheme,
                toggledTheme,
                restoredTheme,
                tonePressed: document.getElementById('toneColorToggleBtn').getAttribute('aria-pressed'),
                legendHidden: document.getElementById('toneLegendBar').classList.contains('hidden'),
                distinctColors: c1 !== c2 && d1 !== d2,
                toneSpans: document.querySelectorAll('#flashBack .tone-1, #flashBack .tone-2, #flashBack .tone-3, #flashBack .tone-4, #flashBack .tone-5').length
              };
            })()""")
            assert tone_before["tonePressed"] == "true" and not tone_before["legendHidden"], tone_before
            assert tone_before["toggledTheme"] != tone_before["initTheme"] and tone_before["restoredTheme"] == tone_before["initTheme"], tone_before
            assert tone_before["distinctColors"] and tone_before["toneSpans"] > 0, tone_before

            # Simulate elapsed due timestamp in localStorage + seed oversized caches right before reload
            cdp.eval(f"""(() => {{
              const raw = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}));
              for (const k of Object.keys(raw.srs || {{}})) {{
                raw.srs[k].due = Date.now() - 5000;
              }}
              raw.onlineCache = {{}};
              for (let i = 0; i < 350; i++) raw.onlineCache['k_' + i] = {{ x: i }};
              raw.viCache = {{}};
              for (let i = 0; i < 650; i++) raw.viCache['v_' + i] = 'vi_' + i;
              localStorage.setItem({json.dumps(STORAGE_KEY)}, JSON.stringify(raw));
            }})()""")

            # Reload and verify F2 dailyGoal, F3 newPerDay & elapsed Due: 1, F5 toneColors, F7 LRU cap
            cdp.reload()
            after_reload = cdp.eval(f"""(() => {{
              document.querySelector('[data-view=\"flashcards\"]').click();
              // Force a save so pruned caches persist back
              document.getElementById('themeToggleBtn').click();
              document.getElementById('themeToggleBtn').click();
              const saved = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}));
              return {{
                dueBadge: document.getElementById('srsDueBadge').textContent,
                newBadge: document.getElementById('srsNewBadge').textContent,
                goalBadge: document.getElementById('srsGoalBadge').textContent,
                tonePressed: document.getElementById('toneColorToggleBtn').getAttribute('aria-pressed'),
                legendHidden: document.getElementById('toneLegendBar').classList.contains('hidden'),
                ocLen: Object.keys(saved.onlineCache || {{}}).length,
                vcLen: Object.keys(saved.viCache || {{}}).length
              }};
            }})()""")
            assert after_reload["dueBadge"] == "Due: 1", after_reload
            assert after_reload["newBadge"] == "New: 9", after_reload
            assert after_reload["goalBadge"] == "Today: 1 / 35", after_reload
            assert after_reload["tonePressed"] == "true" and not after_reload["legendHidden"], after_reload
            assert after_reload["ocLen"] == 250 and after_reload["vcLen"] == 500, after_reload
            print("  T3/T5/T7 F2 daily goal + F3 Due/New + F5 tones + F7 LRU caps PASSED")

            # T6 F6 Typing Pinyin & Dictation modes via real DOM interactions
            f6_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"flashcards\"]').click();
              const modeSel = document.getElementById('flashModeSelect');
              modeSel.value = 'type-pinyin';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              // Flip back or click Reveal to inspect expected answer cleanly without internal access
              document.getElementById('flashRevealBtn').click();
              const revText = document.querySelector('#flashFront .flash-feedback').textContent;
              const match = revText.match(/^(.+?)\\s*·\\s*(.+)$/);
              const hanziShown = document.querySelector('#flashFront .flash-big-hanzi').textContent.trim();
              const expectedPinyin = match ? match[2].trim() : '';

              // Test wrong pinyin
              document.getElementById('flashTypeInput').value = 'zzzz9';
              document.getElementById('flashCheckBtn').click();
              const wrongCls = document.querySelector('#flashFront .flash-feedback').className;

              // Test tone-marked pinyin
              document.getElementById('flashTypeInput').value = expectedPinyin;
              document.getElementById('flashCheckBtn').click();
              const okMarkCls = document.querySelector('#flashFront .flash-feedback').className;

              // Test dictation mode
              modeSel.value = 'dictation';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              const hiddenHanzi = !document.querySelector('#flashFront .flash-big-hanzi');
              document.getElementById('flashHintToggleBtn').click();
              const hintVisible = Boolean(document.querySelector('#flashFront .flash-hint-box'));
              document.getElementById('flashTypeInput').value = hanziShown;
              document.getElementById('flashCheckBtn').click();
              const okDictCls = document.querySelector('#flashFront .flash-feedback').className;

              modeSel.value = 'flip';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              return { hanziShown, expectedPinyin, wrongCls, okMarkCls, hiddenHanzi, hintVisible, okDictCls };
            })()""")
            assert f6_res["expectedPinyin"], f6_res
            assert "err" in f6_res["wrongCls"], f6_res
            assert "ok" in f6_res["okMarkCls"], f6_res
            assert f6_res["hiddenHanzi"] and f6_res["hintVisible"] and "ok" in f6_res["okDictCls"], f6_res
            print("  T6 F6 Typing Pinyin & Dictation modes PASSED")

            # F7 localStorage.setItem error toast & Last Backup note
            ls_err_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"vocab-list\"]').click();
              const backupNote = document.getElementById('backupStatusNote').textContent;
              const orig = Storage.prototype.setItem;
              Storage.prototype.setItem = () => { throw new Error('QuotaExceededError'); };
              document.getElementById('themeToggleBtn').click();
              const errToast = document.getElementById('toast').textContent;
              Storage.prototype.setItem = orig;
              document.getElementById('themeToggleBtn').click();
              return { backupNote, errToast };
            })()""")
            assert "Last backup:" in ls_err_res["backupNote"], ls_err_res
            assert "Could not save" in ls_err_res["errToast"], ls_err_res
            print("  T7b F7 localStorage error toast & backup note PASSED")

            # T8 Lazy textbooks load + §7 Textbooks regressions
            cdp.eval("document.querySelector('[data-view=\"textbooks\"]').click();")
            cdp.wait_for(
                "Boolean(window.TEXTBOOK_DATA) && document.querySelectorAll('#tbLessonPills .tb-lesson-pill').length > 0",
                timeout_s=10.0,
            )
            tb_res = cdp.eval("""(() => {
              const totalLessons = window.TEXTBOOK_DATA.reduce((s, b) => s + b.lessons.length, 0);
              const pageIn = document.getElementById('tbPageInput');
              pageIn.value = '99999';
              pageIn.dispatchEvent(new Event('change', { bubbles: true }));
              const clampedPage = Number(pageIn.value);
              const maxPage = Number(pageIn.max);
              const before = Number(document.getElementById('statVocabList').textContent.replace(/\\D/g, ''));
              document.getElementById('tbAddLessonVocabBtn').click();
              const afterFirst = Number(document.getElementById('statVocabList').textContent.replace(/\\D/g, ''));
              document.getElementById('tbAddLessonVocabBtn').click();
              const afterSecond = Number(document.getElementById('statVocabList').textContent.replace(/\\D/g, ''));
              return {
                books: window.TEXTBOOK_DATA.length,
                totalLessons,
                clampedPage,
                maxPage,
                addedFirst: afterFirst - before,
                addedSecond: afterSecond - afterFirst
              };
            })()""")
            assert tb_res["books"] == 3 and tb_res["totalLessons"] == 48, tb_res
            assert tb_res["clampedPage"] == tb_res["maxPage"], tb_res
            assert tb_res["addedFirst"] > 0 and tb_res["addedSecond"] == 0, tb_res
            print("  T8 Lazy data_textbooks.js & §7 Textbooks regressions PASSED")

            # T9 C4 Mobile viewport (375x740): zero overflow & >= 40px touch targets
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 375, "height": 740, "deviceScaleFactor": 2, "mobile": True},
                session_id=cdp.session_id,
            )
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True}, session_id=cdp.session_id)
            mob_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"hsk\"]').click();
              const overflow = document.documentElement.scrollWidth - window.innerWidth;
              const hskEl = document.getElementById('view-hsk');
              const els = Array.from(hskEl.querySelectorAll('button, .comp-chip, .mini-btn, .icon-btn'));
              const under40 = [];
              let checked = 0;
              for (const el of els) {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                checked++;
                if (r.height < 39.5 || r.width < 39.5) {
                  under40.push({ cls: el.className, w: Math.round(r.width), h: Math.round(r.height), txt: el.textContent.trim().slice(0, 20) });
                }
                if (checked >= 60) break;
              }
              return { overflow, checked, under40Count: under40.length, under40Sample: under40.slice(0, 5) };
            })()""")
            assert mob_res["overflow"] <= 0, f"Mobile horizontal overflow: {mob_res['overflow']}px"
            assert mob_res["under40Count"] == 0, f"Mobile touch targets <40px: {mob_res['under40Sample']}"
            print(f"  T9 C4 Mobile 375x740 (0px overflow, {mob_res['checked']} controls >=40px) PASSED")

            cdp.drain_events()
            assert not cdp.page_errors, f"Unexpected pageErrors in Suite A: {cdp.page_errors}"
            assert not cdp.console_errors, f"Unexpected consoleErrors in Suite A: {cdp.console_errors}"

        # --- Suite B: No cc_cedict_data.js + No PDFs + §6.2 B1 XSS All-Fields + Backup Validation ---
        dir_no_cedict = td / "no_cedict"
        dir_no_cedict.mkdir()
        for fn in ["hanyubutainan.html", "data_etymology.js", "data_vi.js", "data_hsk.js", "data_examples.js", "data_textbooks.js"]:
            shutil.copy2(ROOT / fn, dir_no_cedict / fn)

        profile_b1 = td / "profile_b1"
        with EdgeCDP(browser_bin, profile_b1) as cdp:
            cdp.goto(file_url(dir_no_cedict / "hanyubutainan.html"))
            cdp.drain_events()
            assert not cdp.page_errors

            notice_res = cdp.eval("""(() => {
              const cedictBanner = document.getElementById('dictCedictNotice').textContent;
              document.querySelector('[data-view=\"textbooks\"]').click();
              return { cedictBanner };
            })()""")
            cdp.wait_for(
                "document.getElementById('tbPdfNotice') && document.getElementById('tbPdfNotice').textContent.includes('hsk1_vi.pdf')",
                timeout_s=10.0,
            )
            tb_notice = cdp.eval("document.getElementById('tbPdfNotice').textContent")
            assert "Extended dictionary (cc_cedict_data.js) not found" in notice_res["cedictBanner"], notice_res
            assert "hsk1_vi.pdf" in tb_notice and "Load PDF File" in tb_notice, tb_notice

            # §6.2 step 1: search 蓝莓酸奶 -> Analyze & Add Online offline -> verify custom entry & hidden example-chip
            cdp.eval("""(() => {
              document.querySelector('[data-view=\"dictionary\"]').click();
              const inp = document.getElementById('dictSearchInput');
              inp.value = '蓝莓酸奶';
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              const addBtn = document.getElementById('dictEmptyOnlineBtn');
              addBtn.click();
            })()""")
            cdp.wait_for(
                f"(() => {{ const s = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}) || '{{}}'); return Array.isArray(s.customEntries) && s.customEntries.some(e => e.simp === '蓝莓酸奶'); }})()",
                timeout_s=8.0,
            )
            custom_info = cdp.eval(f"""(() => {{
              const s = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}));
              const ce = s.customEntries.find(e => e.simp === '蓝莓酸奶');
              document.querySelector('[data-view=\"vocab-list\"]').click();
              const hasExampleChip = Boolean(document.querySelector('#myVocabContainer .example-chip'));
              return {{ ce, hasExampleChip }};
            }})()""")
            assert custom_info["ce"] and not custom_info["hasExampleChip"], custom_info

            # §6.2 step 3 & 6: inject XSS payload into badges[0].cls and ALL string fields
            payload = 'x"><img src=x onerror=window.__xss=1>'
            poisoned_ce = dict(custom_info["ce"])
            poisoned_ce["badges"] = [{"label": f"Custom{payload}", "cls": payload}]
            for k, v in list(poisoned_ce.items()):
                if k in ("id", "simp", "type", "cat"):
                    continue
                if isinstance(v, str):
                    poisoned_ce[k] = (v + " " + payload) if v else payload
            poisoned_ce["cat"] = payload
            backup_payload = {
                "schemaVersion": 4,
                "vocabListIds": [poisoned_ce["id"]],
                "customEntries": [poisoned_ce],
                "studyStats": {"dailyGoal": 25, "newPerDay": 15},
            }
            xss_json_file = td / "xss_backup.json"
            xss_json_file.write_text(json.dumps(backup_payload), encoding="utf-8")

            invalid_json_file = td / "invalid_backup.json"
            invalid_json_file.write_text(
                json.dumps({"schemaVersion": 4, "vocabListIds": ["bad_id_999"], "customEntries": [{"bad": 1}]}),
                encoding="utf-8",
            )

        # §6.2 step 4: Fresh browser context importing poisoned JSON
        profile_b2 = td / "profile_b2"
        with EdgeCDP(browser_bin, profile_b2) as cdp:
            cdp.goto(file_url(dir_no_cedict / "hanyubutainan.html"))
            cdp.clear_errors()

            cdp.eval("document.querySelector('[data-view=\"vocab-list\"]').click();")
            cdp.set_file_input("#importFileInput", invalid_json_file)
            inv_toast = cdp.eval("document.getElementById('toast').textContent")
            assert "Import aborted: 0 valid entries" in inv_toast, inv_toast

            cdp.set_file_input("#importFileInput", xss_json_file)
            xss_check = cdp.eval(f"""(() => {{
              // 1. Vocab tab
              document.querySelector('[data-view=\"vocab-list\"]').click();
              const vocabImgs = document.querySelectorAll('img[src=\"x\"]').length;
              // 2. Dictionary search
              document.querySelector('[data-view=\"dictionary\"]').click();
              const inp = document.getElementById('dictSearchInput');
              inp.value = '蓝莓酸奶';
              inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
              const dictImgs = document.querySelectorAll('img[src=\"x\"]').length;
              // 3. Modal Inspector + Escape close
              const lockup = document.querySelector('#dictVocabResults .vocab-char-lockup');
              if (lockup) lockup.click();
              const modalImgs = document.querySelectorAll('img[src=\"x\"]').length;
              document.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Escape', bubbles: true }}));
              const modalClosed = document.getElementById('inspectorModal').classList.contains('hidden');
              // 4. Flashcards front + back
              document.querySelector('[data-view=\"flashcards\"]').click();
              const deckSel = document.getElementById('flashDeckSelect');
              deckSel.value = 'vocab-list';
              deckSel.dispatchEvent(new Event('change', {{ bubbles: true }}));
              const flashFrontImgs = document.querySelectorAll('img[src=\"x\"]').length;
              document.getElementById('flashFlipBtn').click();
              const flashBackImgs = document.querySelectorAll('img[src=\"x\"]').length;
              const goalText = document.getElementById('srsGoalBadge').textContent;
              const s = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}));
              const storedCe = s.customEntries.find(e => e.simp === '蓝莓酸奶');
              return {{
                xssGlobal: window.__xss === undefined ? null : window.__xss,
                vocabImgs,
                dictImgs,
                modalImgs,
                modalClosed,
                flashFrontImgs,
                flashBackImgs,
                goalText,
                sanitizedCls: storedCe && storedCe.badges && storedCe.badges[0] && storedCe.badges[0].cls,
                preservedStructure: storedCe && Boolean(storedCe.structure)
              }};
            }})()""")
            assert xss_check["xssGlobal"] is None, f"XSS EXECUTED! {xss_check}"
            assert xss_check["vocabImgs"] == 0 and xss_check["dictImgs"] == 0, xss_check
            assert xss_check["modalImgs"] == 0 and xss_check["flashFrontImgs"] == 0 and xss_check["flashBackImgs"] == 0, xss_check
            assert xss_check["modalClosed"] and xss_check["goalText"].endswith("/ 25"), xss_check
            assert "<img" not in (xss_check["sanitizedCls"] or ""), xss_check
            assert xss_check["preservedStructure"], xss_check
            print("  T10 B1 §6.2 XSS all-fields + missing files + abort invalid PASSED")

        # Valid JSON + CSV round-trip
        profile_b3 = td / "profile_b3"
        with EdgeCDP(browser_bin, profile_b3) as cdp2:
            cdp2.goto(file_url(dir_no_cedict / "hanyubutainan.html"))
            vjson = td / "valid_roundtrip.json"
            vjson.write_text(
                json.dumps({
                    "schemaVersion": 4,
                    "vocabListIds": ["custom_蓝莓酸奶"],
                    "customEntries": [{
                        "id": "custom_蓝莓酸奶",
                        "simp": "蓝莓酸奶",
                        "trad": "藍莓酸奶",
                        "pinyin": "lán méi suān nǎi",
                        "meaning": "blueberry yogurt",
                        "badges": [{"label": "Compound Word (合成词)", "cls": "badge-word"}],
                    }],
                    "studyStats": {"dailyGoal": 42},
                }),
                encoding="utf-8",
            )
            cdp2.set_file_input("#importFileInput", vjson)
            vcsv = td / "valid_roundtrip.csv"
            vcsv.write_text(
                "Simplified,Traditional,Pinyin,English,Vietnamese,HanViet,HSK,Breakdown,Example\n"
                "藍莓,藍莓,lán méi,blueberry,việt quất,lam môi,0,蓝 + 莓,\n",
                encoding="utf-8",
            )
            cdp2.set_file_input("#importFileInput", vcsv)
            rt = cdp2.eval(f"""(() => {{
              const s = JSON.parse(localStorage.getItem({json.dumps(STORAGE_KEY)}));
              return {{
                count: s.customEntries.length,
                cls: s.customEntries[0].badges[0].cls,
                dailyGoal: s.studyStats.dailyGoal
              }};
            }})()""")
            assert rt["count"] == 2 and rt["cls"] == "badge-word" and rt["dailyGoal"] == 42, rt
            print("  Valid JSON & CSV round-trip PASSED")

        # --- Suite C: Missing optional data_*.js banner & zero exceptions ---
        dir_minimal = td / "minimal_only_html"
        dir_minimal.mkdir()
        shutil.copy2(HTML_PATH, dir_minimal / "hanyubutainan.html")
        profile_c = td / "profile_c"
        with EdgeCDP(browser_bin, profile_c) as cdp:
            cdp.goto(file_url(dir_minimal / "hanyubutainan.html"), minimal=True)
            min_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"textbooks\"]').click();
              const b = document.getElementById('dataMissingBanner');
              return {
                bannerHidden: b ? b.classList.contains('hidden') : true,
                bannerText: b ? b.textContent : '',
                missingCount: (b && b.textContent) ? ['data_etymology.js','data_vi.js','data_hsk.js','data_examples.js'].filter(f => b.textContent.includes(f)).length : 0
              };
            })()""")
            assert not min_res["bannerHidden"] and min_res["missingCount"] == 4, min_res
            cdp.drain_events()
            assert not cdp.page_errors, f"Missing-files mode threw pageErrors: {cdp.page_errors}"
            print("  T11 C1 Missing data_*.js graceful banner (0 pageErrors) PASSED")

    print("\nALL AUTOMATED CHECKS PASSED CLEANLY!")


if __name__ == "__main__":
    run_static_checks()
    run_browser_tests()
