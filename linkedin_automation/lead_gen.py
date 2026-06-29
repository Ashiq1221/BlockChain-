from playwright.sync_api import Page
from urllib.parse import urlencode
from utils import human_delay, save_lead, increment_stat, get_today_stats
from config import LIMITS, DELAY_SHORT, DELAY_MEDIUM, DELAY_LONG


def build_people_search_url(keywords: str = "", title: str = "",
                             company: str = "", location: str = "") -> str:
    """Build a LinkedIn people search URL."""
    params = {"keywords": keywords}
    if title:
        params["title"] = title
    if company:
        params["company"] = company
    if location:
        params["geoUrn"] = location
    return "https://www.linkedin.com/search/results/people/?" + urlencode(params)


def scrape_profiles(page: Page, search_url: str, max_profiles: int = 50) -> list:
    """
    Scrape LinkedIn profile data from search results.
    Returns list of profile dicts.
    """
    print(f"[LeadGen] Scraping profiles from search results...")
    page.goto(search_url)
    human_delay(DELAY_MEDIUM)

    profiles = []
    page_num = 1

    while len(profiles) < max_profiles:
        print(f"[LeadGen] Page {page_num} — collected {len(profiles)} profiles so far")

        result_items = page.query_selector_all(".reusable-search__result-container")
        if not result_items:
            print("[LeadGen] No results found on this page.")
            break

        for item in result_items:
            if len(profiles) >= max_profiles:
                break
            try:
                name_el = item.query_selector(".entity-result__title-text a span[aria-hidden='true']")
                title_el = item.query_selector(".entity-result__primary-subtitle")
                company_el = item.query_selector(".entity-result__secondary-subtitle")
                location_el = item.query_selector(".entity-result__tertiary-subtitle")
                link_el = item.query_selector(".entity-result__title-text a")

                name = name_el.inner_text().strip() if name_el else ""
                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location = location_el.inner_text().strip() if location_el else ""
                profile_url = link_el.get_attribute("href") if link_el else ""
                if profile_url and "?" in profile_url:
                    profile_url = profile_url.split("?")[0]

                if name and profile_url:
                    profile = {
                        "name": name,
                        "title": title,
                        "company": company,
                        "location": location,
                        "profile_url": profile_url,
                    }
                    profiles.append(profile)
                    save_lead(name, title, company, location, profile_url)
                    print(f"[LeadGen]   + {name} | {title} | {company}")

            except Exception as e:
                print(f"[LeadGen] Error parsing profile: {e}")

            human_delay(DELAY_SHORT)

        # Go to next page
        next_btn = page.query_selector("button[aria-label='Next']")
        if next_btn and not next_btn.is_disabled():
            next_btn.click()
            human_delay(DELAY_MEDIUM)
            page_num += 1
        else:
            break

    print(f"[LeadGen] Scraped {len(profiles)} profiles total.")
    return profiles


def view_profile(page: Page, profile_url: str) -> dict:
    """
    Visit a LinkedIn profile and extract detailed info.
    """
    stats = get_today_stats()
    if stats["profile_views"] >= LIMITS["profile_views"]:
        print(f"[LeadGen] Daily profile view limit reached.")
        return {}

    page.goto(profile_url)
    human_delay(DELAY_MEDIUM)
    increment_stat("profile_views")

    try:
        name_el = page.query_selector("h1.text-heading-xlarge")
        headline_el = page.query_selector(".text-body-medium.break-words")
        location_el = page.query_selector(".text-body-small.inline.t-black--light.break-words")

        name = name_el.inner_text().strip() if name_el else ""
        headline = headline_el.inner_text().strip() if headline_el else ""
        location = location_el.inner_text().strip() if location_el else ""

        # Scrape experience
        experience = []
        exp_items = page.query_selector_all("#experience ~ .pvs-list__outer-container li")
        for exp in exp_items[:3]:
            title_el = exp.query_selector("span[aria-hidden='true']")
            if title_el:
                experience.append(title_el.inner_text().strip())

        return {
            "name": name,
            "headline": headline,
            "location": location,
            "experience": experience,
            "profile_url": profile_url,
        }
    except Exception as e:
        print(f"[LeadGen] Error viewing profile {profile_url}: {e}")
        return {}


def run_lead_gen(page: Page, keywords: str = "", title: str = "",
                 company: str = "", location: str = "",
                 max_profiles: int = 50) -> list:
    """Main function: search for and collect LinkedIn leads."""
    print(f"\n[LeadGen] Starting lead generation...")
    print(f"  Keywords : {keywords or '(none)'}")
    print(f"  Title    : {title or '(any)'}")
    print(f"  Company  : {company or '(any)'}")
    print(f"  Location : {location or '(any)'}")

    search_url = build_people_search_url(keywords, title, company, location)
    profiles = scrape_profiles(page, search_url, max_profiles)

    print(f"\n[LeadGen] Done. {len(profiles)} leads saved to leads.csv and database.")
    return profiles
