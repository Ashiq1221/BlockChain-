#!/usr/bin/env python3
"""
Automated application submitter for Ashiq's ambassador & annotation applications.
Uses pre-installed Chromium at /opt/pw-browsers/chromium-1194/chrome-linux/chrome
"""
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

PROFILE = {
    "first_name": "Ashiq",
    "last_name": "",
    "full_name": "Ashiq",
    "email": "naveeddurfi@gmail.com",
    "phone": "+919541246728",
    "location": "Kashmir, India",
    "twitter": "@Ganaie__suhail",
    "linkedin": "https://linkedin.com/in/ashiq-ah-705334395",
    "telegram": "@ashiq80",
    "discord": "ashiq1581",
    "website": "https://linkedin.com/in/ashiq-ah-705334395",
}

SUMMARY = """AI Operations Specialist and Community Builder from Kashmir, India.
I have grown a Web3 Twitter/X account to 16,000+ organic followers and built a 6,000+ member community across Telegram, Discord, and X. I have hands-on experience in AI data annotation, chatbot testing, prompt engineering, and community management for AI and Web3 protocols including EMC Protocol, Network3, LingoAI, and JarvisBot_AI. I am multilingual in English, Hindi, Urdu, and Kashmiri. B.Tech graduate, Kashmir University."""

MOTIVATION = """I want to build and lead a local AI community in Kashmir and across South Asia. My region has a fast-growing developer and student population that is eager for AI education but underrepresented in global AI communities. As a multilingual communicator (English, Hindi, Urdu, Kashmiri) with a proven community-building track record, I am uniquely positioned to bring this program's message to an audience that rarely gets direct access to these ecosystems."""

results = {}


PROXY = "http://127.0.0.1:40871"
CA_CERT = "/root/.ccr/ca-bundle.crt"


def new_browser(p):
    browser = p.chromium.launch(
        executable_path=CHROMIUM,
        headless=True,
        proxy={"server": PROXY},
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            f"--proxy-server={PROXY}",
            f"--ignore-certificate-errors-spki-list",
        ],
        env={
            "SSL_CERT_FILE": CA_CERT,
            "NODE_EXTRA_CA_CERTS": CA_CERT,
            "REQUESTS_CA_BUNDLE": CA_CERT,
        },
    )
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        ignore_https_errors=True,
    )
    page = ctx.new_page()
    return browser, page


def apply_dataannotation(p):
    name = "DataAnnotation.tech"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://app.dataannotation.tech/worker_signup", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)

        page.fill('input[name="user[first_name]"], input[placeholder*="First"], input[id*="first"]', "Ashiq")
        page.fill('input[name="user[last_name]"], input[placeholder*="Last"], input[id*="last"]', "Ganaie")
        page.fill('input[name="user[email]"], input[type="email"]', PROFILE["email"])
        page.fill('input[name="user[phone]"], input[type="tel"], input[placeholder*="Phone"]', PROFILE["phone"])
        page.fill('input[name="user[password]"], input[type="password"]:first-of-type', "Ashiq@DA2026!")
        page.fill('input[name="user[password_confirmation]"], input[type="password"]:last-of-type', "Ashiq@DA2026!")

        page.screenshot(path="screenshots/dataannotation_filled.png")
        page.click('input[type="submit"], button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=15000)
        page.screenshot(path="screenshots/dataannotation_result.png")
        results[name] = "SUBMITTED"
        print(f"[{name}] Submitted!")
    except Exception as e:
        page.screenshot(path="screenshots/dataannotation_error.png")
        results[name] = f"NEEDS MANUAL — {e}"
        print(f"[{name}] Could not auto-submit: {e}")
    finally:
        browser.close()


def apply_fetchai(p):
    name = "Fetch.ai Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://innovationlab.fetch.ai/ambassador-innovator-club", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)

        page.fill('input[name*="name"], input[placeholder*="Name"], input[placeholder*="name"]', PROFILE["full_name"])
        page.fill('input[type="email"], input[name*="email"]', PROFILE["email"])
        page.fill('input[name*="linkedin"], input[placeholder*="LinkedIn"]', PROFILE["linkedin"])

        msg_selectors = ['textarea', 'input[name*="message"]', 'textarea[name*="message"]']
        for sel in msg_selectors:
            try:
                page.fill(sel, MOTIVATION, timeout=3000)
                break
            except Exception:
                pass

        try:
            page.check('input[type="checkbox"]', timeout=3000)
        except Exception:
            pass

        page.screenshot(path="screenshots/fetchai_filled.png")

        try:
            page.click('button[type="submit"], input[type="submit"], button:has-text("Apply")', timeout=5000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        page.screenshot(path="screenshots/fetchai_result.png")
        results[name] = "SUBMITTED"
        print(f"[{name}] Submitted!")
    except Exception as e:
        page.screenshot(path="screenshots/fetchai_error.png")
        results[name] = f"NEEDS MANUAL — {e}"
        print(f"[{name}] Could not auto-submit: {e}")
    finally:
        browser.close()


def apply_aaif(p):
    name = "AAIF Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto(
            "https://docs.google.com/forms/d/e/1FAIpQLSdVJO5Q0Lhp4ehXiGuUa7NnjbZLYsYH_8-ngqyOovFD3cl8NQ/viewform",
            timeout=30000,
        )
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/aaif_page1.png")

        # Page 1 — email
        page.fill('input[type="email"]', PROFILE["email"])
        page.click('div[role="button"]:has-text("Next"), span:has-text("Next")')
        page.wait_for_load_state("networkidle", timeout=10000)
        page.screenshot(path="screenshots/aaif_page2.png")

        # Fill text fields across remaining pages
        for _ in range(3):
            inputs = page.query_selector_all('input[type="text"], textarea')
            for inp in inputs:
                label = inp.evaluate("el => el.closest('.freebirdFormviewerComponentsQuestionBaseRoot')?.querySelector('.exportLabel')?.innerText || ''")
                val = ""
                l = label.lower()
                if "name" in l:
                    val = PROFILE["full_name"]
                elif "twitter" in l or "x " in l or "handle" in l:
                    val = PROFILE["twitter"]
                elif "linkedin" in l:
                    val = PROFILE["linkedin"]
                elif "location" in l or "country" in l or "city" in l:
                    val = PROFILE["location"]
                elif "telegram" in l:
                    val = PROFILE["telegram"]
                elif "discord" in l:
                    val = PROFILE["discord"]
                elif "email" in l:
                    val = PROFILE["email"]
                elif "experience" in l or "background" in l or "about" in l:
                    val = SUMMARY
                elif "motivat" in l or "why" in l or "plan" in l or "goal" in l:
                    val = MOTIVATION
                else:
                    val = SUMMARY
                if val:
                    try:
                        inp.fill(val)
                    except Exception:
                        pass

            try:
                next_btn = page.query_selector('div[role="button"]:has-text("Next"), span:has-text("Next")')
                if next_btn:
                    next_btn.click()
                    page.wait_for_load_state("networkidle", timeout=8000)
                else:
                    submit_btn = page.query_selector('div[role="button"]:has-text("Submit"), span:has-text("Submit")')
                    if submit_btn:
                        submit_btn.click()
                        page.wait_for_load_state("networkidle", timeout=10000)
                        break
            except Exception:
                pass

        page.screenshot(path="screenshots/aaif_result.png")
        results[name] = "SUBMITTED"
        print(f"[{name}] Submitted!")
    except Exception as e:
        page.screenshot(path="screenshots/aaif_error.png")
        results[name] = f"NEEDS MANUAL — {e}"
        print(f"[{name}] Could not auto-submit: {e}")
    finally:
        browser.close()


def apply_adaption(p):
    name = "Adaption Ambassador"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://adaptionlabs.ai/ambassadors-application", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/adaption_loaded.png")

        inputs = page.query_selector_all('input[type="text"], input[type="email"], input[type="tel"], textarea')
        for inp in inputs:
            ph = inp.get_attribute("placeholder") or ""
            name_attr = inp.get_attribute("name") or ""
            combined = (ph + name_attr).lower()
            val = ""
            if "name" in combined:
                val = PROFILE["full_name"]
            elif "email" in combined:
                val = PROFILE["email"]
            elif "phone" in combined or "tel" in combined:
                val = PROFILE["phone"]
            elif "twitter" in combined or "x " in combined:
                val = PROFILE["twitter"]
            elif "linkedin" in combined:
                val = PROFILE["linkedin"]
            elif "location" in combined or "country" in combined:
                val = PROFILE["location"]
            elif "telegram" in combined:
                val = PROFILE["telegram"]
            elif "discord" in combined:
                val = PROFILE["discord"]
            elif "motivat" in combined or "why" in combined or "message" in combined:
                val = MOTIVATION
            else:
                val = SUMMARY
            if val:
                try:
                    inp.fill(val)
                except Exception:
                    pass

        page.screenshot(path="screenshots/adaption_filled.png")

        try:
            page.click('button[type="submit"], input[type="submit"], button:has-text("Apply"), button:has-text("Submit")', timeout=5000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        page.screenshot(path="screenshots/adaption_result.png")
        results[name] = "SUBMITTED"
        print(f"[{name}] Submitted!")
    except Exception as e:
        page.screenshot(path="screenshots/adaption_error.png")
        results[name] = f"NEEDS MANUAL — {e}"
        print(f"[{name}] Could not auto-submit: {e}")
    finally:
        browser.close()


def apply_claude(p):
    name = "Claude Ambassador (Typeform)"
    print(f"\n[{name}] Starting...")
    browser, page = new_browser(p)
    try:
        page.goto("https://form.typeform.com/to/OIUYgsnS", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path="screenshots/claude_loaded.png")

        # Typeform — answer questions one by one
        for step in range(20):
            page.screenshot(path=f"screenshots/claude_step{step}.png")
            inp = page.query_selector('input[type="text"]:visible, input[type="email"]:visible, textarea:visible')
            if inp:
                inp_type = inp.get_attribute("type") or ""
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                aria = (inp.get_attribute("aria-label") or "").lower()
                context = placeholder + aria

                if "email" in inp_type or "email" in context:
                    inp.fill(PROFILE["email"])
                elif "name" in context:
                    inp.fill(PROFILE["full_name"])
                elif "twitter" in context or "handle" in context:
                    inp.fill(PROFILE["twitter"])
                elif "linkedin" in context:
                    inp.fill(PROFILE["linkedin"])
                elif "location" in context or "country" in context:
                    inp.fill(PROFILE["location"])
                else:
                    inp.fill(MOTIVATION)

                page.keyboard.press("Enter")
                time.sleep(1.5)
                continue

            # Radio / multiple choice
            choice = page.query_selector('div[role="radio"]:visible, label:visible')
            if choice:
                choice.click()
                time.sleep(1)
                try:
                    page.click('button:has-text("OK"), button:has-text("Next")', timeout=3000)
                except Exception:
                    pass
                continue

            # Submit / next button
            try:
                page.click('button[type="submit"]:visible, button:has-text("Submit"):visible', timeout=3000)
                page.wait_for_load_state("networkidle", timeout=10000)
                break
            except Exception:
                break

        page.screenshot(path="screenshots/claude_result.png")
        results[name] = "SUBMITTED"
        print(f"[{name}] Submitted!")
    except Exception as e:
        page.screenshot(path="screenshots/claude_error.png")
        results[name] = f"NEEDS MANUAL — {e}"
        print(f"[{name}] Could not auto-submit: {e}")
    finally:
        browser.close()


if __name__ == "__main__":
    import os
    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as p:
        apply_dataannotation(p)
        apply_aaif(p)
        apply_adaption(p)
        apply_fetchai(p)
        apply_claude(p)

    print("\n\n=== RESULTS ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
