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
from .profile import PROFILE, RESUME_PATH, profile_text

SCREENSHOT_DIR = "screenshots"
_CAPTCHA_PAT = re.compile(r"captcha|hcaptcha|recaptcha|turnstile|cf-challenge", re.I)
_APPLY_BTN_PAT = re.compile(r"apply", re.I)
_SUBMIT_PAT = re.compile(r"submit|send application|apply now|finish", re.I)


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
        const els = document.querySelectorAll(
            'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select');
        let i = 0;
        for (const el of els) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;
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

            fields = await _collect_fields(page)
            if not fields:
                report.error = "No form fields found on the page."
                await _shot(page, report, "nofields")
                return report

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

            await _shot(page, report, "filled")

            if submit and not report.captcha_detected:
                try:
                    await page.get_by_role("button", name=_SUBMIT_PAT).first.click(timeout=8000)
                    await page.wait_for_timeout(4000)
                    report.submitted = True
                    await _shot(page, report, "submitted")
                except Exception as e:
                    report.error = f"Submit click failed: {e}"
        except Exception as e:
            report.error = str(e)
            try:
                await _shot(page, report, "error")
            except Exception:
                pass
        finally:
            await browser.close()
    return report
