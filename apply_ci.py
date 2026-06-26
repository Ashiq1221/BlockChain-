#!/usr/bin/env python3
"""
CI version of the application submitter — runs on GitHub Actions with full internet access.
No custom Chromium path, no proxy needed.
"""
import os
import time
import json
from playwright.sync_api import sync_playwright

os.makedirs("screenshots", exist_ok=True)

PROFILE = {
    "first_name": "Ashiq",
    "last_name": "Ganaie",
    "full_name": "Ashiq",
    "email": "naveeddurfi@gmail.com",
    "phone": "+919541246728",
    "location": "Kashmir, India",
    "country": "India",
    "twitter": "@Ganaie__suhail",
    "linkedin": "https://linkedin.com/in/ashiq-ah-705334395",
    "telegram": "@ashiq80",
    "discord": "ashiq1581",
    "github": "https://github.com/ashiq1221",
    "university": "Kashmir University",
    "degree": "Bachelor of Technology (B.Tech)",
    "graduation": "2023",
    "password": "Ashiq@DA2026!",
}

SUMMARY = "AI Operations Specialist and Community Builder from Kashmir, India. Grew a Web3 Twitter/X account to 16,000+ organic followers and built a 6,000+ member community across Telegram, Discord, and X. Hands-on experience in AI data annotation, chatbot testing, prompt engineering, and community management for AI and Web3 protocols including EMC Protocol, Network3, LingoAI, and JarvisBot_AI. Multilingual: English, Hindi, Urdu, Kashmiri. B.Tech, Kashmir University."

MOTIVATION = "I want to build and lead a local AI community in Kashmir and across South Asia. My region has a fast-growing developer and student population that is eager for AI education but underrepresented in global AI communities. As a multilingual communicator (English, Hindi, Urdu, Kashmiri) with a proven community-building track record — 16,000+ organic X followers and a 6,000+ member community — I am uniquely positioned to extend this program's message to South Asian audiences who rarely get direct access to these ecosystems."

results = {}


def new_browser(p):
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    return browser, ctx.new_page()


def smart_fill(page, fields_map):
    """Fill all inputs/textareas on page using label/placeholder/name context."""
    selectors = 'input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]), textarea'
    for el in page.query_selector_all(selectors):
        try:
            ph = (el.get_attribute("placeholder") or "").lower()
            name = (el.get_attribute("name") or "").lower()
            aria = (el.get_attribute("aria-label") or "").lower()
            itype = (el.get_attribute("type") or "text").lower()
            label_el = el.evaluate("""el => {
                const c = el.closest('.field, .form-group, [class*="field"], [class*="input"], [class*="question"]');
                return c ? c.innerText : '';
            }""").lower()
            ctx = " ".join([ph, name, aria, label_el])

            val = ""
            if itype == "email" or "email" in ctx: val = PROFILE["email"]
            elif "first" in ctx and "name" in ctx: val = PROFILE["first_name"]
            elif "last" in ctx and "name" in ctx: val = PROFILE["last_name"]
            elif "full" in ctx and "name" in ctx: val = PROFILE["full_name"]
            elif "name" in ctx and not val: val = PROFILE["full_name"]
            elif itype == "tel" or "phone" in ctx or "mobile" in ctx: val = PROFILE["phone"]
            elif "twitter" in ctx or "x handle" in ctx or "handle" in ctx: val = PROFILE["twitter"]
            elif "linkedin" in ctx: val = PROFILE["linkedin"]
            elif "telegram" in ctx: val = PROFILE["telegram"]
            elif "discord" in ctx: val = PROFILE["discord"]
            elif "github" in ctx: val = PROFILE["github"]
            elif "university" in ctx or "school" in ctx or "institution" in ctx: val = PROFILE["university"]
            elif "degree" in ctx or "major" in ctx: val = PROFILE["degree"]
            elif "graduat" in ctx or "year" in ctx: val = PROFILE["graduation"]
            elif "location" in ctx or "city" in ctx or "country" in ctx or "region" in ctx: val = PROFILE["location"]
            elif "motivat" in ctx or "why" in ctx or "plan" in ctx or "goal" in ctx or "interest" in ctx: val = MOTIVATION
            elif "experience" in ctx or "background" in ctx or "about" in ctx or "bio" in ctx or "skill" in ctx: val = SUMMARY
            elif "message" in ctx or "tell us" in ctx: val = MOTIVATION
            elif el.evaluate("el => el.tagName") == "TEXTAREA": val = MOTIVATION

            if val:
                el.fill(val)
        except Exception:
            pass

    # Checkboxes
    for cb in page.query_selector_all('input[type="checkbox"]'):
        try:
            if not cb.is_checked():
                cb.check()
        except Exception:
            pass


def apply_dataannotation(p):
    name = "DataAnnotation.tech"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://app.dataannotation.tech/worker_signup", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/01_dataannotation_loaded.png")

        smart_fill(page, {})

        # Passwords specifically
        pws = page.query_selector_all('input[type="password"]')
        for pw in pws:
            try: pw.fill(PROFILE["password"])
            except Exception: pass

        page.screenshot(path="screenshots/01_dataannotation_filled.png")

        btn = page.query_selector('input[type="submit"], button[type="submit"]')
        if btn:
            btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

        page.screenshot(path="screenshots/01_dataannotation_result.png")
        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path=f"screenshots/01_dataannotation_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


def apply_aaif(p):
    name = "AAIF Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://docs.google.com/forms/d/e/1FAIpQLSdVJO5Q0Lhp4ehXiGuUa7NnjbZLYsYH_8-ngqyOovFD3cl8NQ/viewform", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)

        for step in range(5):
            page.screenshot(path=f"screenshots/02_aaif_step{step}.png")
            smart_fill(page, {})
            time.sleep(1)

            # Try Next or Submit
            btns = page.query_selector_all('[role="button"]')
            next_btn = next((b for b in btns if "next" in (b.inner_text() or "").lower()), None)
            submit_btn = next((b for b in btns if "submit" in (b.inner_text() or "").lower()), None)

            if submit_btn:
                submit_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                page.screenshot(path="screenshots/02_aaif_submitted.png")
                break
            elif next_btn:
                next_btn.click()
                time.sleep(2)
            else:
                break

        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path="screenshots/02_aaif_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


def apply_adaption(p):
    name = "Adaption Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://adaptionlabs.ai/ambassadors-application", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/03_adaption_loaded.png")
        smart_fill(page, {})
        page.screenshot(path="screenshots/03_adaption_filled.png")

        btn = page.query_selector('button[type="submit"], input[type="submit"]') or \
              next((b for b in page.query_selector_all("button") if re.search(r"submit|apply|send", b.inner_text(), re.I)), None)
        if btn:
            btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

        page.screenshot(path="screenshots/03_adaption_result.png")
        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path="screenshots/03_adaption_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


def apply_fetchai(p):
    name = "Fetch.ai Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://innovationlab.fetch.ai/ambassador-innovator-club", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/04_fetchai_loaded.png")
        smart_fill(page, {})
        page.screenshot(path="screenshots/04_fetchai_filled.png")

        btn = page.query_selector('button[type="submit"], input[type="submit"]')
        if btn:
            btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

        page.screenshot(path="screenshots/04_fetchai_result.png")
        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path="screenshots/04_fetchai_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


def apply_claude_typeform(p):
    name = "Claude Ambassador (Typeform)"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://form.typeform.com/to/OIUYgsnS", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)

        for step in range(20):
            page.screenshot(path=f"screenshots/05_claude_step{step:02d}.png")
            time.sleep(2)

            # Fill visible inputs
            for inp in page.query_selector_all('input[type="text"]:visible, input[type="email"]:visible, textarea:visible'):
                try:
                    aria = (inp.get_attribute("aria-label") or "").lower()
                    ph = (inp.get_attribute("placeholder") or "").lower()
                    itype = (inp.get_attribute("type") or "").lower()
                    ctx = aria + " " + ph

                    if itype == "email" or "email" in ctx: val = PROFILE["email"]
                    elif "name" in ctx: val = PROFILE["full_name"]
                    elif "twitter" in ctx or "handle" in ctx: val = PROFILE["twitter"]
                    elif "linkedin" in ctx: val = PROFILE["linkedin"]
                    elif "location" in ctx or "country" in ctx: val = PROFILE["location"]
                    else: val = MOTIVATION

                    inp.fill(val)
                    time.sleep(0.5)
                    inp.press("Enter")
                    time.sleep(1.5)
                    break
                except Exception:
                    pass

            # Check for submit
            try:
                submit = page.query_selector('[data-qa="submit-button"]:visible, button[type="submit"]:visible')
                if submit:
                    submit.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.screenshot(path="screenshots/05_claude_submitted.png")
                    break
            except Exception:
                pass

            # Try OK button
            try:
                ok = page.query_selector('[data-qa="ok-button"]:visible, button:has-text("OK"):visible')
                if ok:
                    ok.click()
                    time.sleep(1.5)
            except Exception:
                pass

        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path="screenshots/05_claude_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


def apply_qwen(p):
    name = "Qwen Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://qwen.ai/ambassador", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/06_qwen_loaded.png")
        smart_fill(page, {})
        page.screenshot(path="screenshots/06_qwen_filled.png")

        btn = page.query_selector('button[type="submit"], input[type="submit"]')
        if btn:
            btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

        page.screenshot(path="screenshots/06_qwen_result.png")
        results[name] = "SUBMITTED ✅"
        print(f"[{name}] Done!")
    except Exception as e:
        try: page.screenshot(path="screenshots/06_qwen_error.png")
        except Exception: pass
        results[name] = f"FAILED ❌ — {e}"
        print(f"[{name}] Failed: {e}")
    finally:
        browser.close()


if __name__ == "__main__":
    import re
    with sync_playwright() as p:
        apply_dataannotation(p)
        apply_aaif(p)
        apply_adaption(p)
        apply_fetchai(p)
        apply_claude_typeform(p)
        apply_qwen(p)

    print("\n\n" + "="*50)
    print("RESULTS SUMMARY")
    print("="*50)
    for k, v in results.items():
        print(f"  {k}: {v}")

    # Write results as JSON for the Actions summary
    with open("screenshots/results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\nScreenshots uploaded as workflow artifact.")
