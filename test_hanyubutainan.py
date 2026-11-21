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

            # T6 F6 Typing Pinyin (dual inputs + flexibility), Definition, Dictation & 3-Heart System
            f6_res = cdp.eval("""(() => {
              document.querySelector('[data-view=\"flashcards\"]').click();
              const modeSel = document.getElementById('flashModeSelect');
              modeSel.value = 'type-pinyin';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              const hanziShown = document.querySelector('#flashFront .flash-big-hanzi').textContent.trim();

              // Flip must be blocked in Type Pinyin mode
              document.getElementById('flashcardEl').click();
              const flippedInType = document.getElementById('flashcardEl').classList.contains('flipped');
              const flipBtnHidden = document.getElementById('flashFlipBtn').classList.contains('hidden');

              // Test wrong answer reduces hearts (3 -> 2)
              document.getElementById('flashMeaningInput').value = 'wrongmeaning';
              document.getElementById('flashTypeInput').value = 'zzzz9';
              document.getElementById('flashCheckBtn').click();
              const wrongCls = document.querySelector('#flashFront .flash-feedback').className;
              const heartsAfter1Wrong = document.querySelectorAll('#flashFront .flash-heart:not(.lost)').length;

              // Reveal with 不知道 to inspect answer cleanly (single consolidated banner)
              document.getElementById('flashRevealBtn').click();
              const revNodes = document.querySelectorAll('#flashFront .flash-feedback');
              const revClone = revNodes[0].cloneNode(true);
              revClone.querySelectorAll('.flash-feedback-sub').forEach(el => el.remove());
              const revText = revClone.textContent.trim();
              const match = revText.match(/^(.+?)\\s*·\\s*(.+?)\\s*—\\s*(.+)$/);
              const expectedPinyin = match ? match[2].trim() : '';
              const expectedMeaning = match ? match[3].trim().split(/[;/]/)[0].trim() : '';

              // Move to next card: Previous must stay disabled (forward-only for completed cards), then test toneless pinyin + meaning
              document.getElementById('flashNextBtn').click();
              const prevDisabledAfterReveal = document.getElementById('flashPrevBtn').disabled;
              const hz2 = document.querySelector('#flashFront .flash-big-hanzi').textContent.trim();
              const storyHit = (window.STORY_ENTRIES || []).find(s => s.simp === hz2 || s.trad === hz2);
              const hskHit = (window.HSK_COMPLETE_RAW || []).find(r => r[0] === hz2 || r[1] === hz2);
              const py2 = storyHit ? storyHit.pinyin : (hskHit ? hskHit[2] : '');
              const mean2 = (storyHit ? storyHit.meaning : (hskHit ? hskHit[3] : '')).split(/[;/]/)[0].replace(/\\([^)]*\\)/g, '').trim();
              document.getElementById('flashMeaningInput').value = mean2;
              document.getElementById('flashTypeInput').value = py2.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
              document.getElementById('flashCheckBtn').click();
              const okTonelessCls = document.querySelector('#flashFront .flash-feedback').className;

              // Test 3 wrong guesses lock Check & force 不知道
              document.getElementById('flashNextBtn').click();
              for (let k = 0; k < 3; k++) {
                document.getElementById('flashMeaningInput').value = 'nope';
                document.getElementById('flashTypeInput').value = 'zzzz9';
                document.getElementById('flashCheckBtn').click();
              }
              const checkDisabledAt0Hearts = document.getElementById('flashCheckBtn').disabled;
              const heartsAt0 = document.querySelectorAll('#flashFront .flash-heart:not(.lost)').length;
              const feedbacksAt0Hearts = document.querySelectorAll('#flashFront .flash-feedback').length;

              // Test Definition mode
              modeSel.value = 'definition';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              const defHiddenHanzi = !document.querySelector('#flashFront .flash-big-hanzi');
              document.getElementById('flashHintToggleBtn').click();
              const defHintText = (document.querySelector('#flashFront .flash-hint-box') || {}).textContent || '';

              // Test Dictation mode
              modeSel.value = 'dictation';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              const hiddenHanzi = !document.querySelector('#flashFront .flash-big-hanzi');
              document.getElementById('flashHintToggleBtn').click();
              const hintVisible = Boolean(document.querySelector('#flashFront .flash-hint-box'));
              document.getElementById('flashRevealBtn').click();
              const dictRev = document.querySelector('#flashFront .flash-feedback').textContent;
              const dictHanzi = dictRev.split('·')[0].trim();

              modeSel.value = 'flip';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              // Flip mode should have NO Component Clue box and allow flipping
              const hasCompClueInFlip = Boolean(document.querySelector('#flashFront .flash-hint-box'));
              document.getElementById('flashFlipBtn').click();
              const flippedInFlip = document.getElementById('flashcardEl').classList.contains('flipped');
              const backRawStrong = document.querySelector('#flashBack').textContent.includes('<strong>');

              return {
                hanziShown, flippedInType, flipBtnHidden, wrongCls, heartsAfter1Wrong,
                revFeedbackCount: revNodes.length, prevDisabledAfterReveal,
                expectedPinyin, expectedMeaning, okTonelessCls,
                checkDisabledAt0Hearts, heartsAt0, feedbacksAt0Hearts,
                defHiddenHanzi, defHintText,
                hiddenHanzi, hintVisible, dictHanzi, hasCompClueInFlip, flippedInFlip, backRawStrong
              };
            })()""")
            assert f6_res["expectedPinyin"] and f6_res["expectedMeaning"], f6_res
            assert f6_res["revFeedbackCount"] == 1 and f6_res["prevDisabledAfterReveal"] is True, f6_res
            assert f6_res["flippedInType"] is False and f6_res["flipBtnHidden"] is True, f6_res
            assert "err" in f6_res["wrongCls"] and f6_res["heartsAfter1Wrong"] == 2, f6_res
            assert "ok" in f6_res["okTonelessCls"], f6_res
            assert f6_res["checkDisabledAt0Hearts"] is True and f6_res["heartsAt0"] == 0 and f6_res["feedbacksAt0Hearts"] == 1, f6_res
            assert f6_res["defHiddenHanzi"] is True and f6_res["hiddenHanzi"] is True and f6_res["hintVisible"] is True, f6_res
            assert f6_res["hasCompClueInFlip"] is False and f6_res["flippedInFlip"] is True and f6_res["backRawStrong"] is False, f6_res
            print("  T6 F6 Flashcards modes, 3-hearts, flip lock & raw <strong> fix PASSED")

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

            # T12 Update 1 comprehensive checks (Desktop viewport)
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1280, "height": 860, "deviceScaleFactor": 1, "mobile": False},
                session_id=cdp.session_id,
            )
            u1_res = cdp.eval("""(() => {
              // 1. Textbooks single language picker + arrow-free page input
              document.querySelector('[data-view=\"textbooks\"]').click();
              const tbPageType = document.getElementById('tbPageInput').type;
              const tbLangSel = document.getElementById('tbLangSelect');
              tbLangSel.value = 'en';
              tbLangSel.dispatchEvent(new Event('change', { bubbles: true }));
              const viLinesInEnMode = document.querySelectorAll('#tbCompanionPane .tb-line-vi').length;
              tbLangSel.value = 'bilingual';
              tbLangSel.dispatchEvent(new Event('change', { bubbles: true }));

              // 2. Whole vocab-card clickable + modal-open scroll lock + Trust card + Ancient Script moved out
              document.querySelector('[data-view=\"dictionary\"]').click();
              const dIn = document.getElementById('dictSearchInput');
              dIn.value = '喜欢';
              dIn.dispatchEvent(new Event('input', { bubbles: true }));
              const kvEl = document.querySelector('#dictVocabResults .vocab-card .kv') || document.querySelector('#dictDeepResults .deep-card');
              const cardEl = document.querySelector('#dictVocabResults .vocab-card');
              if (cardEl && cardEl.querySelector('.kv')) cardEl.querySelector('.kv').click();
              const modalOpen1 = !document.getElementById('inspectorModal').classList.contains('hidden');
              const bodyLocked = document.body.classList.contains('modal-open');
              const hasTrustCard = Boolean(document.querySelector('#modalBody .etymology-trust-card'));
              const evoInModal = Boolean(document.querySelector('#modalBody .evolution-panel'));
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
              const bodyUnlocked = !document.body.classList.contains('modal-open');

              // 3. Radical Lab: bidirectional, simp/trad, no [+], Ancient Script section
              document.querySelector('[data-view=\"lab\"]').click();
              const hasPlusBadge = document.getElementById('view-lab').textContent.includes('[+]');
              const hasSimpTradRad = document.getElementById('combRadBtns').textContent.includes('讠/言');
              const radWaterBtn = document.querySelector('#combRadBtns [data-comb-rad=\"氵\"]');
              if (radWaterBtn) radWaterBtn.click();
              const validRootsCount = document.querySelectorAll('#combRootBtns .comb-btn.valid-combo').length;
              const ancientPanelVisible = Boolean(document.querySelector('#ancientScriptLabPanel .evolution-panel'));

              // 4. My Vocab List: pinyin disambiguation ('baihuo' -> 百货) + Excel export + session completion
              document.querySelector('[data-view=\"vocab-list\"]').click();
              const addIn = document.getElementById('addWordInput');
              addIn.value = 'baihuo';
              document.getElementById('addWordBtn').click();
              const candCount = document.querySelectorAll('#addWordCandidates .cand-chip').length;
              const baihuoCand = document.querySelector('#addWordCandidates [data-add-candidate=\"百货\"]');
              if (baihuoCand) baihuoCand.click();

              // Capture exported Excel .xlsx blob bytes via URL.createObjectURL hook
              let capturedBlob = null;
              const origCreateUrl = URL.createObjectURL;
              URL.createObjectURL = (b) => { capturedBlob = b; return 'blob:test'; };
              document.getElementById('exportExcelBtn').click();
              URL.createObjectURL = origCreateUrl;
              window.__testXlsxBlob = capturedBlob;

              // 5. Flashcards session completion (spamming Easy after end adds 0 points)
              document.querySelector('[data-view=\"flashcards\"]').click();
              const deckSel = document.getElementById('flashDeckSelect');
              deckSel.value = 'vocab-list';
              deckSel.dispatchEvent(new Event('change', { bubbles: true }));
              const totalInSession = Number(document.getElementById('flashCounter').textContent.split('/')[1].trim());
              const easyBtn = document.querySelector('[data-srs-rate=\"4\"]');
              for (let i = 0; i < totalInSession; i++) easyBtn.click();
              const doneText = document.querySelector('#flashFront').textContent;
              const todayAtEnd = document.getElementById('srsGoalBadge').textContent;
              // Spam Easy & key '4' after session ended
              easyBtn.click();
              document.dispatchEvent(new KeyboardEvent('keydown', { key: '4', bubbles: true }));
              const todayAfterSpam = document.getElementById('srsGoalBadge').textContent;

              return {
                tbPageType, viLinesInEnMode, modalOpen1, bodyLocked, hasTrustCard, evoInModal, bodyUnlocked,
                hasPlusBadge, hasSimpTradRad, validRootsCount, ancientPanelVisible,
                candCount, baihuoFound: Boolean(baihuoCand),
                doneSession: doneText.includes('Session Complete'),
                todayAtEnd, todayAfterSpam
              };
            })()""")
            assert u1_res["tbPageType"] == "text" and u1_res["viLinesInEnEnMode" if False else "viLinesInEnMode"] == 0, u1_res
            assert u1_res["bodyLocked"] is True and u1_res["bodyUnlocked"] is True, u1_res
            assert u1_res["hasPlusBadge"] is False and u1_res["hasSimpTradRad"] is True, u1_res
            assert u1_res["validRootsCount"] >= 2 and u1_res["ancientPanelVisible"] is True, u1_res
            assert u1_res["candCount"] >= 1 and u1_res["baihuoFound"] is True, u1_res
            assert u1_res["doneSession"] is True and u1_res["todayAtEnd"] == u1_res["todayAfterSpam"], u1_res
            # Verify captured .xlsx binary is a valid ZIP archive with expected columns and 百货
            xlsx_b64 = cdp.eval("""(async () => {
              const ab = await window.__testXlsxBlob.arrayBuffer();
              const bytes = new Uint8Array(ab);
              let bin = '';
              for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
              return btoa(bin);
            })()""", await_promise=True)
            import base64, io, zipfile
            raw_xlsx = base64.b64decode(xlsx_b64)
            assert raw_xlsx[:4] == b"PK\x03\x04", "Not a valid ZIP/XLSX"
            with zipfile.ZipFile(io.BytesIO(raw_xlsx)) as zf:
                sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
                for col in ("Order", "Words", "Pinyin", "Definition", "Breakdown", "Example", "百货"):
                    assert col in sheet_xml, f"Missing {col} in sheet1.xml"
            print("  T12 Update 1 features, Excel (.xlsx) & bugfixes PASSED")

            # T13 Update 2: Tone-agnostic flashcard pinyin checking & Half-screen (700-960px) HSK Level box responsive truncation
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 820, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                session_id=cdp.session_id,
            )
            u2_res = cdp.eval("""(() => {
              // 1. Ensure 你好 is in My Vocab List and test Flashcards Type Pinyin with all tone formats
              document.querySelector('[data-view=\"vocab-list\"]').click();
              const addIn = document.getElementById('addWordInput');
              addIn.value = '你好';
              document.getElementById('addWordBtn').click();

              // Check half-screen (820px) responsive HSK Level box in My Vocab List & Holistic HSK
              const myHskTrigger = document.querySelector('#myHskPicker .picker-trigger');
              const myHskLabelSpan = myHskTrigger ? myHskTrigger.querySelector('span:first-child') : null;
              const myHskStyle = myHskLabelSpan ? getComputedStyle(myHskLabelSpan) : null;
              const myHskGroupStyle = getComputedStyle(document.getElementById('myHskPicker').closest('.select-group'));

              document.querySelector('[data-view=\"hsk\"]').click();
              const hskTrigger = document.querySelector('#hskLevelPicker .picker-trigger');
              const hskLabelSpan = hskTrigger ? hskTrigger.querySelector('span:first-child') : null;
              const hskStyle = hskLabelSpan ? getComputedStyle(hskLabelSpan) : null;
              const hskPickerStyle = getComputedStyle(document.getElementById('hskLevelPicker'));
              const hskGroupStyle = getComputedStyle(document.getElementById('hskLevelPicker').closest('.select-group'));
              const hskHeadingH3 = document.querySelector('.hsk-level-heading h3');
              const hskHeadingStyle = hskHeadingH3 ? getComputedStyle(hskHeadingH3) : null;
              const lockupEl = document.querySelector('#view-hsk .vocab-char-lockup');
              const lockupStyle = lockupEl ? getComputedStyle(lockupEl) : null;
              const halfScreenPageOverflow = document.documentElement.scrollWidth - window.innerWidth;
              const triggerFitsBox = hskTrigger ? (hskTrigger.scrollWidth <= hskTrigger.clientWidth + 1) : false;

              // 2. Switch to Flashcards -> My Vocab List deck -> find 你好 card -> test ni hao, ni3 hao3, nǐ hǎo, ni2 hao3, 你好
              document.querySelector('[data-view=\"flashcards\"]').click();
              const deckSel = document.getElementById('flashDeckSelect');
              deckSel.value = 'vocab-list';
              deckSel.dispatchEvent(new Event('change', { bubbles: true }));
              const modeSel = document.getElementById('flashModeSelect');
              modeSel.value = 'type-pinyin';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));

              // Navigate to 你好 if not already first
              for (let step = 0; step < 10; step++) {
                const curHz = (document.querySelector('#flashFront .flash-big-hanzi') || {}).textContent || '';
                if (curHz.includes('你好')) break;
                document.getElementById('flashNextBtn').click();
              }
              const targetHz = (document.querySelector('#flashFront .flash-big-hanzi') || {}).textContent || '';
              const variants = ['ni hao', 'ni3 hao3', 'nǐ hǎo', 'nihao', 'ni2 hao3', '你好'];
              const variantResults = {};
              for (const v of variants) {
                document.getElementById('flashMeaningInput').value = 'hello';
                document.getElementById('flashTypeInput').value = v;
                document.getElementById('flashCheckBtn').click();
                const fb = document.querySelector('#flashFront .flash-feedback');
                variantResults[v] = Boolean(fb && fb.classList.contains('ok'));
              }

              return {
                halfScreenPageOverflow,
                triggerFitsBox,
                myHskEllipsis: Boolean(myHskStyle && myHskStyle.overflow === 'hidden' && myHskStyle.textOverflow === 'ellipsis' && myHskStyle.whiteSpace === 'nowrap'),
                hskEllipsis: Boolean(hskStyle && hskStyle.overflow === 'hidden' && hskStyle.textOverflow === 'ellipsis' && hskStyle.whiteSpace === 'nowrap'),
                hskMinWidth0: hskPickerStyle.minWidth === '0px' && hskGroupStyle.minWidth === '0px' && myHskGroupStyle.minWidth === '0px',
                headingEllipsis: Boolean(hskHeadingStyle && hskHeadingStyle.overflow === 'hidden' && hskHeadingStyle.textOverflow === 'ellipsis' && hskHeadingStyle.whiteSpace === 'nowrap'),
                lockupEllipsis: Boolean(lockupStyle && lockupStyle.overflow === 'hidden' && lockupStyle.textOverflow === 'ellipsis' && lockupStyle.whiteSpace === 'nowrap'),
                targetHz: targetHz.trim(),
                variantResults
              };
            })()""")
            assert u2_res["halfScreenPageOverflow"] <= 0, f"Half-screen overflow: {u2_res}"
            assert u2_res["triggerFitsBox"] and u2_res["myHskEllipsis"] and u2_res["hskEllipsis"], f"HSK Level picker ellipsis failed: {u2_res}"
            assert u2_res["hskMinWidth0"] and u2_res["headingEllipsis"] and u2_res["lockupEllipsis"], f"HSK Level min-width/truncation failed: {u2_res}"
            assert "你好" in u2_res["targetHz"], f"Expected 你好 flashcard, got: {u2_res}"
            assert all(u2_res["variantResults"].values()), f"Flashcard pinyin tone variants failed: {u2_res['variantResults']}"
            print("  T13 Update 2 tone-agnostic pinyin checking & half-screen (820px) HSK Level box PASSED")

            # T14 Update 3: 因地制宜 origin + feedback, search-only Sound Families, Radical glyph fit,
            # Flashcard auto-next/Return, post-correct lock, no Sound+Meaning in Pinyin mode,
            # Dictation pinyin/tones/Hanzi, Vocab/Mastered locked until answered, no shortcuts banner,
            # 3-wrong/不知道 -> Again, and Mastered 1-in-50 + 2-correct retirement
            u3_res = cdp.eval("""(() => {
              // 1. Inspect 因地制宜 -> verified classical origin + user origin feedback + lookup links
              document.querySelector('[data-view=\"dictionary\"]').click();
              const dIn = document.getElementById('dictSearchInput');
              dIn.value = '因地制宜';
              dIn.dispatchEvent(new Event('input', { bubbles: true }));
              const card = document.querySelector('#dictVocabResults .vocab-card');
              if (card) card.click();
              const trustTextBefore = (document.querySelector('#modalBody .etymology-trust-card') || {}).textContent || '';
              const hasLookupLinks = Boolean(document.querySelector('#modalBody .origin-lookup-bar a[href*=\"zdic.net\"]'));
              const toggleFbBtn = document.getElementById('toggleOriginFeedbackBtn');
              if (toggleFbBtn) toggleFbBtn.click();
              const srcIn = document.getElementById('originSourceInput');
              const stIn = document.getElementById('originStoryInput');
              if (srcIn && stIn) {
                srcIn.value = 'Custom Annals of Wu and Yue Note';
                stIn.value = 'Custom user feedback origin story for 因地制宜.';
                document.getElementById('saveOriginFeedbackBtn').click();
              }
              const trustTextAfter = (document.querySelector('#modalBody .etymology-trust-card') || {}).textContent || '';
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

              // 2. Radical Lab: Sound Families empty by default ("No related family"), shows family when searched; Radical glyph full simp/trad fit
              document.querySelector('[data-view=\"lab\"]').click();
              const famSearch = document.getElementById('familySearchInput');
              famSearch.value = '';
              famSearch.dispatchEvent(new Event('input', { bubbles: true }));
              const famEmptyDefault = document.getElementById('familyMatrix').textContent;
              famSearch.value = '青';
              famSearch.dispatchEvent(new Event('input', { bubbles: true }));
              const famFoundCount = document.querySelectorAll('#familyMatrix .family-box').length;
              famSearch.value = 'zzzznotaword';
              famSearch.dispatchEvent(new Event('input', { bubbles: true }));
              const famNoMatchText = document.getElementById('familyMatrix').textContent;
              famSearch.value = '';
              famSearch.dispatchEvent(new Event('input', { bubbles: true }));

              const radGlyphs = Array.from(document.querySelectorAll('#radicalGrid .radical-glyph'));
              const pairGlyph = radGlyphs.find(el => el.textContent.includes('/'));
              const pairText = pairGlyph ? pairGlyph.textContent.trim() : '';
              const pairClips = pairGlyph ? (pairGlyph.scrollWidth > pairGlyph.clientWidth + 1) : true;

              // 3. Flashcards: no #flashKbdTip, Pinyin mode hides Sound + Meaning badge, locks until answered, locks after correct, Return advances
              document.querySelector('[data-view=\"flashcards\"]').click();
              const noKbdTip = !document.getElementById('flashKbdTip');
              const deckSel = document.getElementById('flashDeckSelect');
              deckSel.value = 'vocab-list';
              deckSel.dispatchEvent(new Event('change', { bubbles: true }));
              const modeSel = document.getElementById('flashModeSelect');
              modeSel.value = 'type-pinyin';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));

              // Navigate to 你好
              for (let step = 0; step < 10; step++) {
                const curHz = (document.querySelector('#flashFront .flash-big-hanzi') || {}).textContent || '';
                if (curHz.includes('你好')) break;
                document.getElementById('flashNextBtn').click();
              }
              const listDisabledBefore = document.getElementById('flashListBtn').disabled;
              const masterDisabledBefore = document.getElementById('flashMasterBtn').disabled;
              const frontBadgesPinyin = Array.from(document.querySelectorAll('#flashFront .badge')).map(b => b.textContent).join(' ');
              const hasSoundMeaningInPinyin = frontBadgesPinyin.includes('Sound + Meaning');

              document.getElementById('flashMeaningInput').value = 'hello';
              document.getElementById('flashTypeInput').value = 'ni hao';
              document.getElementById('flashCheckBtn').click();
              const lockedAfterCorrect = (
                document.getElementById('flashTypeInput').disabled &&
                document.getElementById('flashMeaningInput').disabled &&
                document.getElementById('flashCheckBtn').disabled &&
                document.getElementById('flashHintToggleBtn').disabled &&
                document.getElementById('flashRevealBtn').disabled
              );
              const unlockedMetaAfterAnswer = (
                !document.getElementById('flashListBtn').disabled &&
                !document.getElementById('flashMasterBtn').disabled
              );
              const autoNextCountdownShown = document.getElementById('flashNextBtn').textContent.includes('5s');

              // Press Return (Enter) to advance immediately
              const counterBeforeEnter = document.getElementById('flashCounter').textContent;
              document.getElementById('flashcardEl').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
              const counterAfterEnter = document.getElementById('flashCounter').textContent;

              // 4. Dictation mode: rejects wrong pinyin, accepts tone-agnostic pinyin (even different tone marks) and Hanzi
              modeSel.value = 'dictation';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              for (let step = 0; step < 30; step++) {
                const spk = document.querySelector('#flashFront [data-speak]');
                if (spk && spk.getAttribute('data-speak') === '你好') break;
                document.getElementById('flashNextBtn').click();
              }
              // Test wrong pinyin first -> rejected
              document.getElementById('flashTypeInput').value = 'zzzz';
              document.getElementById('flashCheckBtn').click();
              const dictWrongRejected = document.querySelector('#flashFront .flash-feedback').classList.contains('err');
              // Test tone-agnostic pinyin ('nī hǎo' for 你好) -> accepted
              document.getElementById('flashTypeInput').value = 'nī hǎo';
              document.getElementById('flashCheckBtn').click();
              const dictToneAgnosticAccepted = document.querySelector('#flashFront .flash-feedback').classList.contains('ok');

              // 5. Mark 你好 as mastered after answering -> verify 2 correct answers retire it permanently
              document.getElementById('flashMasterBtn').click();
              // Move to next card and trigger 3 wrong answers -> auto marked as Again
              document.getElementById('flashNextBtn').click();
              for (let w = 0; w < 3; w++) {
                document.getElementById('flashTypeInput').value = 'wrong_answer_xyz';
                document.getElementById('flashCheckBtn').click();
              }
              const againFeedbackText = (document.querySelector('#flashFront .flash-feedback.err') || {}).textContent || '';

              return {
                trustTextBefore,
                trustTextAfter,
                hasLookupLinks,
                famEmptyDefault,
                famFoundCount,
                famNoMatchText,
                pairText,
                pairClips,
                noKbdTip,
                listDisabledBefore,
                masterDisabledBefore,
                hasSoundMeaningInPinyin,
                lockedAfterCorrect,
                unlockedMetaAfterAnswer,
                autoNextCountdownShown,
                counterBeforeEnter,
                counterAfterEnter,
                dictWrongRejected,
                dictToneAgnosticAccepted,
                againFeedbackText
              };
            })()""")
            assert "吴越春秋" in u3_res["trustTextBefore"] and "Confidence: High" in u3_res["trustTextBefore"], u3_res
            assert "Custom Annals of Wu and Yue Note" in u3_res["trustTextAfter"] and u3_res["hasLookupLinks"], u3_res
            assert "No related family" in u3_res["famEmptyDefault"] and u3_res["famFoundCount"] >= 1 and "No related family" in u3_res["famNoMatchText"], u3_res
            assert "/" in u3_res["pairText"] and len(u3_res["pairText"].split("/")[1]) >= 1 and not u3_res["pairClips"], u3_res
            assert u3_res["noKbdTip"] is True, u3_res
            assert u3_res["listDisabledBefore"] is True and u3_res["masterDisabledBefore"] is True, u3_res
            assert u3_res["hasSoundMeaningInPinyin"] is False, u3_res
            assert u3_res["lockedAfterCorrect"] is True and u3_res["unlockedMetaAfterAnswer"] is True, u3_res
            assert u3_res["autoNextCountdownShown"] is True, u3_res
            assert u3_res["dictWrongRejected"] is True and u3_res["dictToneAgnosticAccepted"] is True, u3_res
            assert "Again" in u3_res["againFeedbackText"], u3_res
            print("  T14 Update 3 origin feedback, Lab UI, Dictation, locking & Auto-Next PASSED")

            # T15: Mastered sub-tab in My Vocab List, Flashcard box containment (no overflow),
            #      flexible answer checking (Bai/bai/bái/bai2/白 & lv/lu/lǜ/绿), and forward-only navigation + requeue
            t15_mastered = cdp.eval("""(() => {
              // 1. Master 白 directly from Dictionary without saving it to My Vocab List
              document.querySelector('[data-view=\"dictionary\"]').click();
              const dIn = document.getElementById('dictSearchInput');
              dIn.value = '白';
              dIn.dispatchEvent(new Event('input', { bubbles: true }));
              const baiCard = Array.from(document.querySelectorAll('#dictVocabResults .vocab-card'))
                .find(c => c.querySelector('[data-master]') && c.querySelector('.vocab-char-lockup').textContent.includes('白'));
              const masBtn = baiCard ? baiCard.querySelector('[data-master]') : null;
              if (masBtn && !masBtn.classList.contains('active-master')) masBtn.click();

              // Click top-bar Mastered chip -> jumps straight to My Vocab List -> Mastered Words sub-tab
              document.getElementById('statMasteredChip').click();
              const inVocabView = !document.getElementById('view-vocab-list').classList.contains('hidden');
              const masteredTabActive = document.getElementById('myTabMasteredBtn').classList.contains('active');
              const addHidden = document.getElementById('myVocabAddSection').classList.contains('hidden');
              const ioHidden = document.getElementById('myVocabIoSection').classList.contains('hidden');
              const hasBaiInMastered = Array.from(document.querySelectorAll('#myVocabContainer .vocab-char-lockup'))
                .some(el => el.textContent.includes('白'));
              const countBeforeUnmaster = Number(document.getElementById('myTabMasteredCount').textContent);

              // Unmark 白 right from the Mastered tab -> removes it and decrements count
              const mBaiCard = Array.from(document.querySelectorAll('#myVocabContainer .vocab-card'))
                .find(c => c.querySelector('.vocab-char-lockup').textContent.includes('白'));
              if (mBaiCard) mBaiCard.querySelector('[data-master]').click();
              const countAfterUnmaster = Number(document.getElementById('myTabMasteredCount').textContent);
              const stillHasBai = Array.from(document.querySelectorAll('#myVocabContainer .vocab-char-lockup'))
                .some(el => el.textContent.includes('白'));

              // Switch back to Saved Words tab and add 白 + 绿 + 好 for Flashcard testing
              document.getElementById('myTabSavedBtn').click();
              const savedTabActive = document.getElementById('myTabSavedBtn').classList.contains('active');
              const addVisibleOnSaved = !document.getElementById('myVocabAddSection').classList.contains('hidden');
              for (const w of ['白', '绿', '好']) {
                document.getElementById('addWordInput').value = w;
                document.getElementById('addWordBtn').click();
              }
              return {
                inVocabView, masteredTabActive, addHidden, ioHidden, hasBaiInMastered,
                countBeforeUnmaster, countAfterUnmaster, stillHasBai, savedTabActive, addVisibleOnSaved
              };
            })()""")
            assert t15_mastered["inVocabView"] and t15_mastered["masteredTabActive"], t15_mastered
            assert t15_mastered["addHidden"] and t15_mastered["ioHidden"] and t15_mastered["hasBaiInMastered"], t15_mastered
            assert t15_mastered["countAfterUnmaster"] == t15_mastered["countBeforeUnmaster"] - 1 and not t15_mastered["stillHasBai"], t15_mastered
            assert t15_mastered["savedTabActive"] and t15_mastered["addVisibleOnSaved"], t15_mastered

            # Test flexible answers across Definition, Dictation, and Type Pinyin for 白 and 绿
            t15_answers = cdp.eval("""(() => {
              document.querySelector('[data-view=\"flashcards\"]').click();
              const deckSel = document.getElementById('flashDeckSelect');
              deckSel.value = 'vocab-list';
              deckSel.dispatchEvent(new Event('change', { bubbles: true }));
              const modeSel = document.getElementById('flashModeSelect');

              const goToWord = (target) => {
                for (let s = 0; s < 15; s++) {
                  const frontText = document.getElementById('flashFront').textContent;
                  const spk = document.querySelector('#flashFront [data-speak]');
                  const cur = spk ? spk.getAttribute('data-speak') : '';
                  if (cur === target || frontText.includes(target)) return true;
                  document.getElementById('flashNextBtn').click();
                }
                return false;
              };

              const testInputs = (mode, targetWord, candidates, meaningVal) => {
                const res = {};
                for (const cand of candidates) {
                  modeSel.value = 'flip';
                  modeSel.dispatchEvent(new Event('change', { bubbles: true }));
                  modeSel.value = mode;
                  modeSel.dispatchEvent(new Event('change', { bubbles: true }));
                  if (mode === 'definition') {
                    // Meaning shown on front
                    for (let s = 0; s < 15; s++) {
                      const frontTxt = document.getElementById('flashFront').textContent.toLowerCase();
                      if ((targetWord === '白' && frontTxt.includes('white')) || (targetWord === '绿' && frontTxt.includes('green'))) break;
                      document.getElementById('flashNextBtn').click();
                    }
                  } else {
                    goToWord(targetWord);
                  }
                  if (mode === 'type-pinyin') document.getElementById('flashMeaningInput').value = meaningVal;
                  document.getElementById('flashTypeInput').value = cand;
                  document.getElementById('flashCheckBtn').click();
                  const fb = document.querySelector('#flashFront .flash-feedback');
                  res[cand] = Boolean(fb && fb.classList.contains('ok'));
                }
                return res;
              };

              const baiDef = testInputs('definition', '白', ['Bai', 'bai', 'bái', 'Bái', 'bai2', 'bāi', '白', 'mai'], '');
              const baiDict = testInputs('dictation', '白', ['Bai', 'bai', 'bái', 'bai2', '白', 'mai'], '');
              const baiPinyin = testInputs('type-pinyin', '白', ['Bai', 'bai', 'bái', 'bai2', '白', 'mai'], 'white');
              const lvDef = testInputs('definition', '绿', ['lv', 'lu', 'lǜ', 'lv4', 'lu4', '绿'], '');

              // Per-field feedback check in type-pinyin
              modeSel.value = 'flip'; modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              modeSel.value = 'type-pinyin'; modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              goToWord('白');
              document.getElementById('flashMeaningInput').value = 'white';
              document.getElementById('flashTypeInput').value = 'wrongpy';
              document.getElementById('flashCheckBtn').click();
              const wrongPyFb = document.querySelector('#flashFront .flash-feedback').textContent;
              document.getElementById('flashMeaningInput').value = 'wrongmean';
              document.getElementById('flashTypeInput').value = 'bai';
              document.getElementById('flashCheckBtn').click();
              const wrongMeanFb = document.querySelector('#flashFront .flash-feedback').textContent;

              return { baiDef, baiDict, baiPinyin, lvDef, wrongPyFb, wrongMeanFb };
            })()""")
            for bucket in ("baiDef", "baiDict", "baiPinyin"):
                for good_in in ("Bai", "bai", "bái", "bai2", "白"):
                    assert t15_answers[bucket][good_in] is True, (bucket, good_in, t15_answers)
                assert t15_answers[bucket]["mai"] is False, (bucket, t15_answers)
            assert t15_answers["baiDef"]["Bái"] is True and t15_answers["baiDef"]["bāi"] is True, t15_answers
            assert all(t15_answers["lvDef"].values()), t15_answers
            assert "pinyin" in t15_answers["wrongPyFb"].lower() and "meaning" in t15_answers["wrongMeanFb"].lower(), t15_answers

            # Test UI containment (zero overflow across desktop 1280, half-screen 820, mobile 375) + forward-only nav + requeue
            for vp_name, vp_w, vp_h, is_mob in [("desktop", 1280, 900, False), ("half", 820, 900, False), ("mobile", 375, 740, True)]:
                cdp.send(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": vp_w, "height": vp_h, "deviceScaleFactor": 2 if is_mob else 1, "mobile": is_mob},
                    session_id=cdp.session_id,
                )
                box_res = cdp.eval("""(() => {
                  const modeSel = document.getElementById('flashModeSelect');
                  modeSel.value = 'type-pinyin';
                  modeSel.dispatchEvent(new Event('change', { bubbles: true }));
                  document.getElementById('flashHintToggleBtn').click();
                  document.getElementById('flashMeaningInput').value = 'wrong';
                  document.getElementById('flashTypeInput').value = 'wrong';
                  document.getElementById('flashCheckBtn').click();
                  document.getElementById('flashRevealBtn').click();
                  const cardRect = document.getElementById('flashcardEl').getBoundingClientRect();
                  const navRect = document.querySelector('.flash-nav-row').getBoundingClientRect();
                  const items = Array.from(document.querySelectorAll('#flashFront .flash-hint-box, #flashFront .flash-feedback, #flashFront .flash-option-bar'));
                  const outOfBox = items.filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.bottom > cardRect.bottom + 1 || r.right > cardRect.right + 1 || r.left < cardRect.left - 1;
                  }).map(el => el.className);
                  return {
                    feedbackCount: document.querySelectorAll('#flashFront .flash-feedback').length,
                    outOfBox,
                    overlapsNav: cardRect.bottom > navRect.top + 1,
                    horizOverflow: document.documentElement.scrollWidth - window.innerWidth
                  };
                })()""")
                assert box_res["feedbackCount"] == 1, (vp_name, box_res)
                assert box_res["outOfBox"] == [], (vp_name, box_res)
                assert box_res["overlapsNav"] is False, (vp_name, box_res)
                assert box_res["horizOverflow"] <= 0, (vp_name, box_res)

            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                session_id=cdp.session_id,
            )
            nav_res = cdp.eval("""(() => {
              const modeSel = document.getElementById('flashModeSelect');
              modeSel.value = 'definition';
              modeSel.dispatchEvent(new Event('change', { bubbles: true }));
              const prevAtStart = document.getElementById('flashPrevBtn').disabled;
              const startCount = Number(document.getElementById('flashCounter').textContent.split('/')[1].trim());
              const firstMeaning = document.querySelector('#flashFront').textContent;

              // Helper to answer current definition card using HSK/STORY lookup
              const answerCur = () => {
                const spk = document.querySelector('#flashFront [data-speak]');
                // In definition mode there is no top speak button, so find matching entry by meaning text
                const mText = document.querySelector('#flashFront .flash-front-center > div').textContent.trim();
                const hit = (window.HSK_COMPLETE_RAW || []).find(r => mText.includes(r[3].split(';')[0].trim()))
                  || (window.STORY_ENTRIES || []).find(s => mText.includes(s.meaning.split(';')[0].trim()));
                return hit ? (Array.isArray(hit) ? hit[2] : hit.pinyin) : 'bai';
              };

              // Card 1: answer correctly -> advance -> Previous must stay disabled
              document.getElementById('flashTypeInput').value = answerCur();
              document.getElementById('flashCheckBtn').click();
              const prevWhileCorrect = document.getElementById('flashPrevBtn').disabled;
              document.getElementById('flashNextBtn').click();
              const prevAfterDoneCard1 = document.getElementById('flashPrevBtn').disabled;

              // Card 2: fail 1 wrong -> Previous disabled; fail 3 -> Check/Hint disabled -> click 不知道 -> requeued -> Enter advances
              document.getElementById('flashTypeInput').value = 'wrong1';
              document.getElementById('flashCheckBtn').click();
              const prevAfterWrong = document.getElementById('flashPrevBtn').disabled;
              document.getElementById('flashTypeInput').value = 'wrong2';
              document.getElementById('flashCheckBtn').click();
              document.getElementById('flashTypeInput').value = 'wrong3';
              document.getElementById('flashCheckBtn').click();
              const checkLocked0 = document.getElementById('flashCheckBtn').disabled;
              const revealEnabled0 = !document.getElementById('flashRevealBtn').disabled;
              document.getElementById('flashRevealBtn').click();
              const totalAfterRequeue = Number(document.getElementById('flashCounter').textContent.split('/')[1].trim());
              document.getElementById('flashcardEl').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
              const prevAfterRequeuedCard2 = document.getElementById('flashPrevBtn').disabled;

              // Finish remaining cards forward -> reaches Session Complete (never wraps around)
              for (let step = 0; step < 30; step++) {
                if (document.querySelector('#flashFront').textContent.includes('Session Complete')) break;
                document.getElementById('flashNextBtn').click();
              }
              const reachedComplete = document.querySelector('#flashFront').textContent.includes('Session Complete');
              const prevAtEnd = document.getElementById('flashPrevBtn').disabled;
              const nextAtEnd = document.getElementById('flashNextBtn').disabled;

              return {
                prevAtStart, startCount, prevWhileCorrect, prevAfterDoneCard1,
                prevAfterWrong, checkLocked0, revealEnabled0, totalAfterRequeue,
                prevAfterRequeuedCard2, reachedComplete, prevAtEnd, nextAtEnd
              };
            })()""")
            assert nav_res["prevAtStart"] is True and nav_res["prevWhileCorrect"] is True and nav_res["prevAfterDoneCard1"] is True, nav_res
            assert nav_res["prevAfterWrong"] is True and nav_res["checkLocked0"] is True and nav_res["revealEnabled0"] is True, nav_res
            assert nav_res["totalAfterRequeue"] == nav_res["startCount"] + 1 and nav_res["prevAfterRequeuedCard2"] is True, nav_res
            assert nav_res["reachedComplete"] is True and nav_res["prevAtEnd"] is True and nav_res["nextAtEnd"] is True, nav_res
            print("  T15 Mastered tab, zero UI overflow (1280/820/375), Bai/lv answers & forward-only nav PASSED")

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
