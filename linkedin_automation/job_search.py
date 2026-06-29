from playwright.sync_api import Page
from urllib.parse import urlencode
from utils import human_delay, save_job, increment_stat, get_today_stats
from config import LIMITS, DELAY_SHORT, DELAY_MEDIUM


def build_job_search_url(keywords: str, location: str, easy_apply_only: bool = True,
                          remote: bool = False, experience: str = None) -> str:
    """Build a LinkedIn jobs search URL with filters."""
    params = {
        "keywords": keywords,
        "location": location,
        "f_LF": "f_AL" if easy_apply_only else "",  # Easy Apply filter
    }
    if remote:
        params["f_WT"] = "2"  # Remote work type
    if experience:
        exp_map = {
            "internship": "1",
            "entry": "2",
            "associate": "3",
            "mid": "4",
            "director": "5",
            "executive": "6",
        }
        params["f_E"] = exp_map.get(experience.lower(), "")

    base_url = "https://www.linkedin.com/jobs/search/?"
    return base_url + urlencode({k: v for k, v in params.items() if v})


def search_jobs(page: Page, keywords: str, location: str,
                easy_apply_only: bool = True, max_jobs: int = 20,
                remote: bool = False) -> list:
    """
    Search for jobs and return a list of job data dicts.
    Does NOT apply — just collects job listings.
    """
    stats = get_today_stats()
    if stats["jobs_applied"] >= LIMITS["job_applications"]:
        print(f"[Jobs] Daily limit reached ({LIMITS['job_applications']} applications). Stopping.")
        return []

    url = build_job_search_url(keywords, location, easy_apply_only, remote)
    print(f"[Jobs] Searching: {keywords} in {location}")
    page.goto(url)
    human_delay(DELAY_MEDIUM)

    jobs = []
    page_num = 1

    while len(jobs) < max_jobs:
        print(f"[Jobs] Scraping page {page_num}...")
        job_cards = page.query_selector_all(".jobs-search-results__list-item")

        if not job_cards:
            print("[Jobs] No more job listings found.")
            break

        for card in job_cards:
            if len(jobs) >= max_jobs:
                break
            try:
                title_el = card.query_selector(".job-card-list__title")
                company_el = card.query_selector(".job-card-container__company-name")
                location_el = card.query_selector(".job-card-container__metadata-item")
                link_el = card.query_selector("a.job-card-list__title")

                title = title_el.inner_text().strip() if title_el else "Unknown"
                company = company_el.inner_text().strip() if company_el else "Unknown"
                location_text = location_el.inner_text().strip() if location_el else "Unknown"
                job_url = link_el.get_attribute("href") if link_el else ""
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.linkedin.com" + job_url

                has_easy_apply = card.query_selector(".job-card-container__apply-method") is not None

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location_text,
                    "url": job_url,
                    "easy_apply": has_easy_apply,
                })
            except Exception as e:
                print(f"[Jobs] Error parsing job card: {e}")
            human_delay(DELAY_SHORT)

        # Try to go to next page
        next_btn = page.query_selector("button[aria-label='Next']")
        if next_btn and not next_btn.is_disabled():
            next_btn.click()
            human_delay(DELAY_MEDIUM)
            page_num += 1
        else:
            break

    print(f"[Jobs] Found {len(jobs)} jobs.")
    return jobs


def apply_to_job(page: Page, job: dict, resume_path: str = None) -> bool:
    """
    Apply to a single Easy Apply job.
    Returns True if successfully applied.
    """
    stats = get_today_stats()
    if stats["jobs_applied"] >= LIMITS["job_applications"]:
        print(f"[Jobs] Daily application limit reached.")
        return False

    print(f"[Jobs] Applying to: {job['title']} at {job['company']}")
    page.goto(job["url"])
    human_delay(DELAY_MEDIUM)

    # Click Easy Apply button
    easy_apply_btn = page.query_selector("button.jobs-apply-button")
    if not easy_apply_btn:
        print(f"[Jobs] No Easy Apply button found for: {job['title']}")
        return False

    easy_apply_btn.click()
    human_delay(DELAY_SHORT)

    # Handle multi-step application form
    max_steps = 10
    step = 0

    while step < max_steps:
        human_delay(DELAY_SHORT)
        step += 1

        # Upload resume if field exists and resume provided
        if resume_path:
            upload_btn = page.query_selector("input[type='file']")
            if upload_btn:
                upload_btn.set_input_files(resume_path)
                human_delay(DELAY_SHORT)

        # Fill phone number if empty
        phone_field = page.query_selector("input[id*='phoneNumber']")
        if phone_field:
            current_val = phone_field.input_value()
            if not current_val:
                phone_field.fill("+1234567890")

        # Check for "Next" or "Submit" or "Review" buttons
        submit_btn = page.query_selector("button[aria-label='Submit application']")
        review_btn = page.query_selector("button[aria-label='Review your application']")
        next_btn = page.query_selector("button[aria-label='Continue to next step']")

        if submit_btn:
            submit_btn.click()
            human_delay(DELAY_MEDIUM)
            print(f"[Jobs] ✅ Applied to {job['title']} at {job['company']}")
            save_job(job["title"], job["company"], job["location"], job["url"])
            increment_stat("jobs_applied")
            return True
        elif review_btn:
            review_btn.click()
        elif next_btn:
            next_btn.click()
        else:
            # Close any open modal and skip
            close_btn = page.query_selector("button[aria-label='Dismiss']")
            if close_btn:
                close_btn.click()
            print(f"[Jobs] ⚠️  Could not complete application for {job['title']}")
            return False

    return False


def run_job_automation(page: Page, keywords: str, location: str,
                       max_apply: int = 10, resume_path: str = None,
                       remote: bool = False):
    """Main function: search jobs and auto-apply to Easy Apply listings."""
    print(f"\n[Jobs] Starting job automation: '{keywords}' in '{location}'")
    jobs = search_jobs(page, keywords, location, easy_apply_only=True,
                       max_jobs=max_apply * 2, remote=remote)

    applied = 0
    skipped = 0

    for job in jobs:
        if applied >= max_apply:
            break
        if not job["easy_apply"]:
            skipped += 1
            continue

        success = apply_to_job(page, job, resume_path)
        if success:
            applied += 1
        human_delay((5, 10))  # longer pause between applications

    print(f"\n[Jobs] Done. Applied: {applied} | Skipped: {skipped}")
    return applied
