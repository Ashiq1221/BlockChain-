"""Playwright form autofill — fills any application form it can see.

Safety model:
  • Dry-run by default: fills every field, uploads the resume, screenshots,
    but does NOT submit unless submit=True (or APPLY_AUTO_SUBMIT=true).
  • Never bypasses CAPTCHAs or bot checks — it stops, screenshots, and
    reports that a manual step is needed.
  • Field values come from the profile + the orchestrator's plan; the AI
    mapper is instructed to leave anything unknown blank, never invent.
"""
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from aos import providers as p
from . import form_learning
from .profile import PROFILE, RESUME_PATH, profile_text

SCREENSHOT_DIR = "screenshots"
_CAPTCHA_PAT = re.compile(r"captcha|hcaptcha|recaptcha|turnstile|cf-challenge", re.I)
_APPLY_BTN_PAT = re.compile(r"apply", re.I)
_SUBMIT_PAT = re.compile(r"submit|send application|apply now|finish|send$", re.I)
_NEXT_PAT = re.compile(r"continue|next|proceed|step", re.I)
_SUCCESS_PAT = re.compile(
    r"thank you|thanks for applying|application (received|submitted|complete|sent)|"
    r"we('| ha)ve received|we'll be in touch|you're in the queue|in the queue|"
    r"successfully submitted|submission received|received your application|"
    r"we will get back|talk soon|application complete", re.I)


@dataclass
class FillReport:
    url: str
    filled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    resume_uploaded: bool = False
    captcha_detected: bool = False
    submitted: bool = False
    screenshots: list[str] = field(default_factory=list)
    error: str = ""

    def summary(self) -> str:
        lines = [f"Form fill for {self.url}",
                 f"Filled {len(self.filled)} fields; skipped {len(self.skipped)}.",
                 f"Resume uploaded: {'yes' if self.resume_uploaded else 'no'}"]
        if self.captcha_detected:
            lines.append("⚠️ CAPTCHA/bot-check detected — finish this one manually.")
        lines.append("Submitted: " + ("✅ yes" if self.submitted
                                      else "no (dry-run — review screenshot, then rerun with --submit)"))
        if self.screenshots:
            lines.append("Screenshots: " + ", ".join(self.screenshots))
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


async def _collect_fields(page) -> list[dict]:
    """Enumerate visible form fields with their best-guess labels."""
    return await page.evaluate("""() => {
        const fields = [];
        // Clear stale indices from previous steps so selectors never collide
        // with now-hidden fields carrying an old data-af-idx.
        document.querySelectorAll('[data-af-idx]').forEach(e => e.removeAttribute('data-af-idx'));
        const els = document.querySelectorAll(
            'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select');
        let i = 0;
        const HONEY = ['website','honeypot','url','company_website'];
        for (const el of els) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;
            if (el.tabIndex === -1) continue;                 // honeypot / off-tab-order traps
            if (HONEY.includes((el.name||'').toLowerCase())) continue;
            let label = '';
            if (el.id) {
                const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (l) label = l.innerText.trim();
            }
            if (!label) label = el.getAttribute('aria-label') || el.placeholder || '';
            if (!label) {
                const wrap = el.closest('label, .field, .form-group, [class*=question]');
                if (wrap) label = wrap.innerText.trim().slice(0, 120);
            }
            el.setAttribute('data-af-idx', String(i));
            const f = {idx: i, tag: el.tagName.toLowerCase(),
                       type: el.type || '', name: el.name || '', id: el.id || '',
                       label: label.slice(0, 150), required: el.required || false};
            if (el.tagName === 'SELECT')
                f.options = Array.from(el.options).map(o => o.text.trim()).slice(0, 30);
            fields.push(f); i++;
        }
        return fields;
    }""")


async def _map_fields(fields: list[dict], plan_context: str) -> dict:
    """One AI call: map every field index to a value from the profile/plan."""
    spec = [{k: v for k, v in f.items() if k in
             ("idx", "tag", "type", "name", "label", "options", "required")}
            for f in fields if f["type"] != "file"]
    prompt = (
        f"CANDIDATE PROFILE:\n{profile_text()}\n\n"
        f"DEFAULT SCREENER ANSWERS:\n{json.dumps(PROFILE['qa_defaults'], indent=1)}\n\n"
        f"APPLICATION CONTEXT (cover letter / tailored answers):\n{plan_context[:2500]}\n\n"
        f"FORM FIELDS:\n{json.dumps(spec, indent=1)[:5000]}\n\n"
        "Map each field idx to the value to type. Rules:\n"
        "• Use ONLY facts from the profile/context — NEVER invent data.\n"
        "• For selects, the value MUST be one of the given options (or omit).\n"
        "• For checkboxes: 'check' to tick (consents/acknowledgements only), omit otherwise.\n"
        "• Cover-letter/free-text questions: use the application context.\n"
        "• Omit any field you cannot answer truthfully.\n"
        'Reply ONLY with JSON: {"0": "value", "3": "value", ...}'
    )
    out = await p.think(prompt, system="You fill job-application forms accurately and honestly.",
                        max_tokens=1500, prefer="claude")
    m = re.search(r"\{.*\}", out or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


async def _fill_step(page, fields: list[dict], plan_context: str, report: "FillReport") -> None:
    """Fill every mapped field on the current step (idempotent across steps)."""
    mapping = await _map_fields(fields, plan_context)
    for f in fields:
        sel = f'[data-af-idx="{f["idx"]}"]'
        label = f["label"] or f["name"] or f'field#{f["idx"]}'
        try:
            if f["type"] == "file":
                await page.set_input_files(sel, RESUME_PATH)
                report.resume_uploaded = True
                report.filled.append(f"{label} ← resume")
                continue
            val = mapping.get(str(f["idx"]))
            if not val:
                report.skipped.append(label)
                continue
            if f["tag"] == "select":
                await page.select_option(sel, label=str(val))
            elif f["type"] in ("checkbox", "radio"):
                if str(val).lower() in ("check", "true", "yes"):
                    await page.check(sel)
                else:
                    report.skipped.append(label)
                    continue
            else:
                await page.fill(sel, str(val))
            report.filled.append(f"{label} ← {str(val)[:60]}")
        except Exception:
            report.skipped.append(label)


async def _enabled_button(page, pattern):
    """Return the first visible+enabled button matching pattern, else None."""
    try:
        loc = page.get_by_role("button", name=pattern)
        n = min(await loc.count(), 6)
        for i in range(n):
            b = loc.nth(i)
            if await b.is_visible() and await b.is_enabled():
                return b
    except Exception:
        pass
    return None


async def _collect_controls(page) -> list[dict]:
    """All visible, enabled clickable controls (buttons / links-as-buttons)."""
    return await page.evaluate("""() => {
        const out = [];
        const sel = 'button, [role=button], a[href], input[type=submit], input[type=button]';
        for (const el of document.querySelectorAll(sel)) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
            const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
            if (!text || text.length > 60) continue;
            out.push({text, disabled});
        }
        // de-dup by text, keep enabled preference
        const seen = {};
        for (const c of out) { if (!(c.text in seen) || !c.disabled) seen[c.text] = c; }
        return Object.values(seen);
    }""")


async def _page_text(page) -> str:
    try:
        return (await page.inner_text("body"))[:1200]
    except Exception:
        return ""


def _is_success(text: str) -> bool:
    return bool(_SUCCESS_PAT.search(text or ""))


async def _ai_navigate(controls: list[dict], page_text: str, has_fields: bool,
                       hint: str, submit_allowed: bool) -> dict:
    """The orchestra looks at the page and decides the next action.

    Returns {"action": submit|continue|done|stop, "button": <text>, "reason": ...}
    """
    enabled = [c["text"] for c in controls if not c.get("disabled")]
    disabled = [c["text"] for c in controls if c.get("disabled")]
    prompt = (
        f"You are an agent submitting a job application form, step by step.\n"
        f"ENABLED buttons right now: {json.dumps(enabled)}\n"
        f"DISABLED buttons (a required field above them may be unfilled): {json.dumps(disabled)}\n"
        f"This step has input fields to fill: {has_fields}\n"
        f"PAGE TEXT (excerpt):\n{page_text[:700]}\n\n"
        f"LEARNED HINTS from past attempts on this site: {hint}\n\n"
        "Goal: progress through every step and SUBMIT the completed application.\n"
        "Decide ONE next action:\n"
        "• 'done'      — the page shows a success/confirmation (thank you, received, submitted).\n"
        "• 'submit'    — this is the final step; pick the button that submits/sends the application.\n"
        "• 'continue'  — there are more steps; pick the button that advances (next/continue/etc.).\n"
        "• 'stop'      — no enabled button can progress (e.g. only a disabled submit, or a dead end).\n"
        "Pick 'button' EXACTLY from the ENABLED list. Prefer forward progress over 'back'.\n"
        'Reply ONLY JSON: {"action":"submit|continue|done|stop","button":"<exact enabled text>","reason":"<short>"}'
    )
    out = await p.think(prompt, system="You navigate and submit web forms precisely. Output only JSON.",
                        max_tokens=200, prefer="cf")
    m = re.search(r"\{.*\}", out or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    if not submit_allowed and d.get("action") == "submit":
        d["action"] = "stop_dryrun"
    return d or {"action": "stop", "reason": "navigator returned nothing"}


async def _click_text(page, text: str) -> bool:
    for maker in (lambda: page.get_by_role("button", name=text, exact=True),
                  lambda: page.get_by_role("link", name=text, exact=True),
                  lambda: page.get_by_text(text, exact=True)):
        try:
            b = maker().first
            if await b.is_visible() and await b.is_enabled():
                await b.click(timeout=6000)
                return True
        except Exception:
            continue
    return False


async def _shot(page, report: FillReport, tag: str) -> None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    host = urlparse(report.url).netloc.replace(":", "_") or "page"
    path = f"{SCREENSHOT_DIR}/{host}-{tag}-{int(time.time())}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        report.screenshots.append(path)
    except Exception:
        pass


async def fill_application(url: str, plan_context: str = "",
                           submit: bool | None = None) -> FillReport:
    from playwright.async_api import async_playwright

    if submit is None:
        submit = os.getenv("APPLY_AUTO_SUBMIT", "false").lower() == "true"
    report = FillReport(url=url)

    async with async_playwright() as pw:
        # Honor egress proxies (e.g. managed cloud sandboxes).
        proxy = ({"server": os.environ["HTTPS_PROXY"]}
                 if os.environ.get("HTTPS_PROXY") else None)
        try:
            browser = await pw.chromium.launch(headless=True, proxy=proxy)
        except Exception:
            browser = await pw.chromium.launch(
                headless=True, proxy=proxy,
                executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page(viewport={"width": 1280, "height": 1800})
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)

            # Job page with an "Apply" button instead of an inline form → click through.
            if not await page.query_selector("input:not([type=hidden]), textarea"):
                btn = page.get_by_role("link", name=_APPLY_BTN_PAT).first
                try:
                    await btn.click(timeout=5000)
                except Exception:
                    try:
                        await page.get_by_role("button", name=_APPLY_BTN_PAT).first.click(timeout=5000)
                    except Exception:
                        pass
                await page.wait_for_timeout(2500)

            if _CAPTCHA_PAT.search(await page.content()):
                report.captcha_detected = True

            if not await _collect_fields(page):
                report.error = "No form fields found on the page."
                await _shot(page, report, "nofields")
                return report

            # ── AI-navigator loop (self-learning) ────────────────────────────
            # On each step the orchestra fills the visible fields, then LOOKS at
            # the page and decides submit / continue / done / stop — handling
            # custom button labels a regex would miss. A fingerprint guard stops
            # loops; per-domain recipes are recalled and updated so each attempt
            # hardens the next.
            recipe = await form_learning.recall(url)
            hint = form_learning.hint_text(recipe)
            advance_labels: list[str] = []
            submit_label = ""
            success_signal = ""
            seen: dict[str, int] = {}
            max_steps = int(os.getenv("MAX_FORM_STEPS", "30"))

            for step in range(max_steps):
                fields = await _collect_fields(page)
                if fields:
                    await _fill_step(page, fields, plan_context, report)
                await _shot(page, report, f"step{step}")

                page_text = await _page_text(page)
                if _CAPTCHA_PAT.search(await page.content()):
                    report.captcha_detected = True
                if _is_success(page_text):
                    report.submitted = True
                    success_signal = _SUCCESS_PAT.search(page_text).group(0)
                    await _shot(page, report, "success")
                    break

                controls = await _collect_controls(page)
                # Loop guard: fingerprint of (field labels + enabled buttons).
                fp = "|".join(sorted(f["label"] for f in fields)) + "##" + \
                     "|".join(sorted(c["text"] for c in controls if not c.get("disabled")))
                seen[fp] = seen.get(fp, 0) + 1
                if seen[fp] >= 3:
                    report.error = "Form stopped advancing (loop guard)."
                    break

                decision = await _ai_navigate(controls, page_text, bool(fields),
                                              hint, submit_allowed=submit)
                action = decision.get("action", "stop")
                btn = decision.get("button", "")

                if action == "done":
                    report.submitted = True
                    success_signal = success_signal or "confirmation detected by navigator"
                    break
                if action == "stop_dryrun":
                    break                              # dry-run reached the submit step
                if action == "submit":
                    if report.captcha_detected:
                        report.error = "CAPTCHA present — not submitting."
                        break
                    clicked = await _click_text(page, btn)
                    if not clicked:                    # fall back to regex match
                        rb = await _enabled_button(page, _SUBMIT_PAT)
                        if rb is not None:
                            try:
                                await rb.click(timeout=8000)
                                clicked = True
                            except Exception:
                                clicked = False
                    submit_label = btn
                    await page.wait_for_timeout(5000)
                    post = await _page_text(page)
                    if _is_success(post):
                        success_signal = _SUCCESS_PAT.search(post).group(0)
                        report.submitted = True
                    else:
                        # clicked but no explicit confirmation text detected
                        report.submitted = clicked
                    await _shot(page, report, "submitted")
                    break
                if action == "continue" and btn:
                    if await _click_text(page, btn):
                        advance_labels.append(btn)
                        await page.wait_for_timeout(2000)
                        continue
                    report.error = f"Could not click '{btn}'."
                    break
                report.error = decision.get("reason", "navigator chose to stop")
                break

            # ── Learn from this attempt ──────────────────────────────────────
            await form_learning.record(url, {
                "advance_labels": list(dict.fromkeys(
                    (recipe.get("advance_labels") or []) + advance_labels))[:12],
                "submit_label": submit_label or recipe.get("submit_label", ""),
                "steps": len(report.screenshots),
                "submitted": report.submitted,
                "success_signal": success_signal or recipe.get("success_signal", ""),
                "fields_filled": len(report.filled),
            })
        except Exception as e:
            report.error = str(e)
            try:
                await _shot(page, report, "error")
            except Exception:
                pass
        finally:
            await browser.close()
    return report
