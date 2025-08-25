# ================================
# 📌 Imports
# ================================

import os, time, json, csv, sys, random, re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import google.generativeai as genai
import pdfplumber
from urllib.parse import quote
import requests


# ================================
# 📌 File Paths (constants)
# ================================
CONFIG_PATH = "config.json"
APPLIED_JOBS_JSON = "applied_jobs.json"
APPLIED_LOG = "applied_jobs.log"
SKIPPED_LOG = "skipped_log.csv"
HR_LOG = "hr_contact_log.txt"  # New log for HR contact info
EXTERNAL_APPLY_LOG = "external_apply_log.csv"  # Log for jobs that require external application


# ================================
# 📌 Config Loader
# ================================
def load_config():
    """Reads config.json which stores user preferences (roles, locations, keywords, pacing)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ================================
# 📌 Resume Reader (MODIFIED FOR PDF)
# ================================
def read_resume():
    """Reads resume text from a PDF file for Gemini prompts from the path specified in .env."""
    resume_path_from_env = os.getenv("RESUME_PATH")
    if not resume_path_from_env:
        raise RuntimeError("RESUME_PATH not set in .env file.")

    full_text = ""
    try:
        with pdfplumber.open(resume_path_from_env) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                full_text += txt + "\n"
        return full_text.strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Resume file not found at: {resume_path_from_env}")
    except Exception as e:
        print(f"Error reading PDF file: {e}")
        return ""


# ================================
# 📌 Playwright Browser Setup
# ================================
def launch_browser(headless=False):
    """
    Launches Playwright Chromium with sane defaults that reduce flakiness.
    Returns (playwright, browser, context, page)
    """
    p = sync_playwright().start()
    args = [
        "--disable-notifications",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-gpu",
        "--disable-infobars",
    ]
    browser = p.chromium.launch(headless=headless, args=args)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        java_script_enabled=True,
        ignore_https_errors=True,
    )
    page = context.new_page()
    return p, browser, context, page


# ================================
# 📌 Naukri Login Automation (MODIFIED)
# =============================
def login(page, email, password):
    """Logs into Naukri with credentials from environment variables."""
    page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#usernameField", timeout=10000)
    except PlaywrightTimeoutError:
        # If login page didn't load properly, retry once
        page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
        page.wait_for_selector("#usernameField", timeout=10000)

    # Occasionally cookie/notification banners appear; try dismissing common ones
    for sel in [
        "button:has-text('Got it')",
        "button:has-text('Allow')",
        "button:has-text('OK')",
        "button:has-text('I agree')",
        "button:has-text('Accept')",
        "button:has-text('Close')",
    ]:
        try:
            if page.locator(sel).first.is_visible():
                page.locator(sel).first.click(timeout=1000)
        except:
            pass

    page.fill("#usernameField", email)
    page.fill("#passwordField", password)
    page.locator("button:has-text('Login')").first.click()
    # Wait for the login form to disappear and the next page to load
    try:
        page.wait_for_selector("#usernameField", state="detached", timeout=20000)
    except:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass


# ================================
# 📌 JSON Tracking of Applied Jobs
# ================================
def load_applied_jobs():
    """Loads already applied job links from JSON (to skip re-applying)."""
    if os.path.exists(APPLIED_JOBS_JSON):
        with open(APPLIED_JOBS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_applied_jobs(applied_jobs):
    """Saves applied jobs into JSON file for persistence."""
    with open(APPLIED_JOBS_JSON, "w", encoding="utf-8") as f:
        json.dump(applied_jobs, f, indent=4)


# ================================
# 📌 Logging Functions
# ================================
def log_applied(job_title, job_link):
    """Logs applied jobs into applied_jobs.log (human-readable)."""
    with open(APPLIED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {job_title} | {job_link}\n")


def log_skipped(job_title, job_link):
    """Logs skipped jobs into skipped_log.csv with timestamp."""
    header_needed = not os.path.exists(SKIPPED_LOG)
    with open(SKIPPED_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["timestamp", "job_title", "job_link"])
        w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job_title, job_link])


def log_hr_contact(job_title, hr_name, contact_info):
    """Logs HR contact info as a fallback."""
    with open(HR_LOG, "a", encoding="utf-8") as f:
        f.write(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Job: {job_title} | HR Name: {hr_name} | Contact Info: {contact_info}\n"
        )


def log_external_application(job_title, company, naukri_link, external_url=""):
    """Logs jobs that require external application (non-Naukri site) to a separate CSV."""
    header_needed = not os.path.exists(EXTERNAL_APPLY_LOG)
    with open(EXTERNAL_APPLY_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["timestamp", "job_title", "company", "naukri_link", "external_url"])
        w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job_title, company or "", naukri_link or "", external_url or ""])


# ================================
# 📌 Utility: Gentle scroll to load dynamic content
# ================================
def lazy_scroll(page, steps=8, pause=500):
    for _ in range(steps):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(pause)


# ================================
# 📌 Scraper (Roles + Keywords + Location filtering) — tuned selectors
# ================================
def scrape_jobs(page, roles, locations, experience):
    """
    Scrapes job listings from Naukri for given roles + locations.
    Filters jobs using keywords from config.json.
    Returns a list of dicts: {"title", "link", "company"}.
    """
    cfg = load_config()
    keywords = cfg.get("keywords", [])
    jobs_out = []
    seen_links = set()

    for role in roles:
        for loc in locations:
            search_url = f"https://www.naukri.com/{role.replace(' ', '-')}-jobs-in-{loc.lower()}?experience={experience}"
            print(f"Searching for '{role}' in '{loc}' at: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass

            # Try to detect job anchors; if not present, scroll a bit
            try:
                page.wait_for_selector("a[href*='naukri.com/job-listings']", timeout=6000)
            except:
                lazy_scroll(page, steps=8, pause=400)

            # Parse DOM with BS4 to collect links and company names robustly
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Candidate selectors for a job card container (expanded)
            card_selectors = [
                "article.jobTuple",
                "div.jobTuple",
                "div.srp-jobtuple",
                "article[data-job-id]",
                "div.row1",  # older
                "div.list",
                "li[data-job-id]",
            ]
            card_nodes = []
            for sel in card_selectors:
                card_nodes = soup.select(sel)
                if card_nodes:
                    break

            # Fallback: try to collect via anchors first if no cards found
            if not card_nodes:
                anchors = soup.select("a.title, a[href*='naukri.com/job-listings'], a[title][href*='job-listings']")
                for a in anchors:
                    title = (a.get_text(strip=True) or "").strip()
                    link = a.get("href")
                    if not link or link in seen_links:
                        continue
                    # Try to find nearby company text
                    company = ""
                    parent = a.find_parent(["article", "div", "li"])
                    if parent:
                        company_el = parent.select_one("a.subTitle, span.subTitle, div.comp-name, span.comp-name, span.companyName")
                        if company_el:
                            company = company_el.get_text(strip=True)
                    job = {"title": title or role, "link": link, "company": company}
                    # Filter with keywords if provided
                    if keywords:
                        blob = f"{title} {company}".lower()
                        if not any(k.lower() in blob for k in keywords):
                            continue
                    jobs_out.append(job)
                    seen_links.add(link)

                # Extra fallback: use Playwright locators to gather job blocks, then parse
                if not anchors:
                    locator = page.locator("article.jobTuple, div.jobTuple, article[data-job-id], div.srp-jobtuple, li[data-job-id]")
                    count = 0
                    try:
                        count = locator.count()
                    except:
                        pass
                    for i in range(min(count, 50)):
                        try:
                            block_html = locator.nth(i).inner_html()
                            block = BeautifulSoup(block_html, "html.parser")
                            a = block.select_one("a.title, a[href*='job-listings']")
                            if not a:
                                continue
                            title = (a.get_text(strip=True) or "").strip()
                            link = a.get("href")
                            if not link or link in seen_links:
                                continue
                            company_el = block.select_one("a.subTitle, span.subTitle, div.comp-name, span.comp-name, span.companyName")
                            company = company_el.get_text(strip=True) if company_el else ""
                            desc = block.get_text(" ", strip=True).lower()
                            if keywords and not any(k.lower() in desc for k in keywords):
                                continue
                            jobs_out.append({"title": title or role, "link": link, "company": company})
                            seen_links.add(link)
                        except:
                            continue

                # Continue to next location/role
                continue

            # Parse structured cards
            for card in card_nodes:
                title_elem = card.select_one("a.title") or card.select_one("a[href*='job-listings']")
                title = title_elem.get_text(strip=True) if title_elem else ""
                link = title_elem.get("href") if title_elem else None
                if not link or link in seen_links:
                    continue

                company_el = (
                    card.select_one("a.subTitle")
                    or card.select_one("span.subTitle")
                    or card.select_one("div.comp-name, span.comp-name, span.companyName")
                )
                company = company_el.get_text(strip=True) if company_el else ""

                # Build description text for keyword filtering
                desc = card.get_text(" ", strip=True).lower()
                title_match = True  # we already search by role in query
                keyword_match = True if not keywords else any(k.lower() in desc for k in keywords)

                if title_match and keyword_match:
                    jobs_out.append({"title": title or role, "link": link, "company": company})
                    seen_links.add(link)
                    print(f"📌 Match: {title} @ {company}")
                else:
                    log_skipped(title, link)
    return jobs_out


# ================================
# 📌 API-based discovery (JSearch + Adzuna)
# ================================
def fetch_jobs_via_api(cfg):
    """
    Fetch jobs via external APIs to reduce scraping maintenance.
    Uses:
      - Adzuna (India): requires ADZUNA_APP_ID and ADZUNA_APP_KEY
      - JSearch (RapidAPI): requires RAPIDAPI_KEY
    Returns a list of dicts: {"title", "link", "company"}.
    """
    roles = cfg.get("roles", [])
    locations = cfg.get("locations", [])
    keywords = [k.lower() for k in cfg.get("keywords", [])]

    # Use experience from config.json as-is for query phrases (if provided)
    exp_val = str(cfg.get("experience", "")).strip()
    exp_phrase = f"{exp_val} years" if exp_val else ""

    out = []
    seen = set()

    # Adzuna
    adz_id = os.getenv("ADZUNA_APP_ID")
    adz_key = os.getenv("ADZUNA_APP_KEY")
    if adz_id and adz_key:
        for role in roles:
            for loc in locations:
                try:
                    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
                    params = {
                        "app_id": adz_id,
                        "app_key": adz_key,
                        "what": f"{role} {exp_phrase}".strip(),
                        "where": loc,
                        "results_per_page": 50,
                        "content-type": "application/json",
                    }
                    r = requests.get(url, params=params, timeout=15)
                    if r.status_code == 200:
                        data = r.json()
                        for item in data.get("results", []):
                            title = item.get("title", "").strip()
                            company = ""
                            comp = item.get("company")
                            if isinstance(comp, dict):
                                company = comp.get("display_name", "") or ""
                            link = item.get("redirect_url")
                            if not link or link in seen:
                                continue
                            if keywords:
                                blob = f"{title} {company}".lower()
                                if not any(k in blob for k in keywords):
                                    continue
                            out.append({"title": title or role, "link": link, "company": company})
                            seen.add(link)
                except Exception as e:
                    print(f"⚠️ Adzuna fetch error for {role} in {loc}: {e}")

    # JSearch (RapidAPI)
    rapid_key = os.getenv("RAPIDAPI_KEY")
    if rapid_key:
        headers = {
            "X-RapidAPI-Key": rapid_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        for role in roles:
            for loc in locations:
                try:
                    q = f"{role} {exp_phrase} in {loc}".strip()
                    q = re.sub(r"\s+", " ", q)
                    url = "https://jsearch.p.rapidapi.com/search"
                    params = {"query": q, "page": "1", "num_pages": "1", "country": "in"}
                    r = requests.get(url, headers=headers, params=params, timeout=20)
                    if r.status_code == 200:
                        data = r.json()
                        for item in data.get("data", []):
                            title = (item.get("job_title") or "").strip()
                            company = (item.get("employer_name") or "").strip()
                            # Select best link available
                            link = item.get("job_apply_link") or item.get("job_post_link") or item.get("job_apply_url")
                            if not link:
                                # Fallback to employer website if present
                                link = item.get("employer_website") or ""
                            if not link or link in seen:
                                continue
                            if keywords:
                                blob = f"{title} {company}".lower()
                                if not any(k in blob for k in keywords):
                                    continue
                            out.append({"title": title or role, "link": link, "company": company})
                            seen.add(link)
                    else:
                        print(f"⚠️ JSearch non-200: {r.status_code}")
                except Exception as e:
                    print(f"⚠️ JSearch fetch error for {role} in {loc}: {e}")

    return out


def dedupe_jobs(jobs):
    """Deduplicate jobs by link."""
    out = []
    seen = set()
    for j in jobs:
        link = j.get("link")
        if not link or link in seen:
            continue
        out.append(j)
        seen.add(link)
    return out


def discover_jobs(page, cfg):
    """
    Discovery wrapper that can use API-based discovery or scraping.
    Selection priority:
      - If JOB_DISCOVERY/env or cfg.discovery == 'api': use API; fallback to scrape if empty
      - If 'hybrid': combine API + scrape and dedupe
      - Else: scrape only (default)
    """
    mode = (os.getenv("JOB_DISCOVERY", cfg.get("discovery", "scrape")) or "scrape").lower()

    if mode == "api":
        api_jobs = fetch_jobs_via_api(cfg)
        if api_jobs:
            print(f"🔎 API discovery found {len(api_jobs)} jobs.")
            return api_jobs
        else:
            print("ℹ️ API returned no jobs; falling back to scrape.")
            return scrape_jobs(page, cfg["roles"], cfg["locations"], cfg.get("experience", "0-1"))

    if mode == "hybrid":
        api_jobs = fetch_jobs_via_api(cfg)
        scraped_jobs = scrape_jobs(page, cfg["roles"], cfg["locations"], cfg.get("experience", "0-1"))
        combined = dedupe_jobs((api_jobs or []) + (scraped_jobs or []))
        print(f"🔎 Hybrid discovery: API {len(api_jobs or [])}, Scrape {len(scraped_jobs or [])}, Combined {len(combined)}.")
        return combined

    # Default: scrape
    return scrape_jobs(page, cfg["roles"], cfg["locations"], cfg.get("experience", "0-1"))


# ================================
# 📌 Gemini Initialization
# ================================
def init_gemini():
    """Initializes Google Gemini API using key from .env file."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env or environment.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


# ================================
# 📌 Gemini Recruiter Message Generation
# ================================
def generate_message(model, resume_text, hr_name, role_hint, job_link, company=None):
    """Generates a short recruiter message using Gemini model."""
    prompt = f"""
You are a concise, professional job applicant.
Write a polite, 90–120 word recruiter message to {hr_name or 'the recruiter'} about a role like "{role_hint}" at {company or 'the company'}.
Use 1–2 resume achievements with metrics and end with a clear CTA to connect/schedule a quick chat.
Reference this job URL: {job_link}
Resume:
{resume_text}
"""
    try:
        resp = model.generate_content(prompt)
        msg = (resp.text or "").strip()
        return msg[:900] if msg else f"Hi {hr_name or 'there'}, I came across the {role_hint} role. Based on my background, I’d love to connect. Thanks!"
    except Exception as e:
        print("Gemini generation failed:", e)
        return f"Hi {hr_name or 'there'}, I noticed the opening for {role_hint}. Based on my Python/AI experience, I'd love to connect. Thanks!"


def linkedin_note_from_message(msg, limit=275):
    """Shorten a long message into a LinkedIn connection note (<= ~275 chars)."""
    msg = " ".join(msg.split())
    if len(msg) <= limit:
        return msg
    return (msg[: limit - 3] + "...").strip()


# ================================
# 📌 LinkedIn Automation (optional fallback messaging)
# ================================
def linkedin_login(context):
    """Logs into LinkedIn using env credentials. Returns a page or None if not configured."""
    li_email = os.getenv("LINKEDIN_EMAIL")
    li_pass = os.getenv("LINKEDIN_PASSWORD")
    if not li_email or not li_pass:
        print("ℹ️ LINKEDIN_EMAIL/PASSWORD not set; skipping LinkedIn messaging.")
        return None

    page = context.new_page()
    try:
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        page.fill("#username", li_email)
        page.fill("#password", li_pass)
        page.click("button[type='submit']")
        try:
            page.wait_for_url(lambda url: "login" not in url, timeout=15000)
        except:
            pass
        # Confirm login by checking for top nav or profile avatar
        try:
            page.wait_for_selector("header, nav", timeout=10000)
        except:
            print("⚠️ LinkedIn login might require OTP/CAPTCHA. Complete it manually if prompted.")
    except Exception as e:
        print(f"⚠️ LinkedIn login failed: {e}")
        return None
    return page


def linkedin_message_recruiter(li_page, message, hr_name=None, company=None):
    """
    Find a recruiter on LinkedIn and send a message or connection note.
    Priority:
      1) If hr_name provided: search hr_name + company (if any).
      2) Else: search 'Recruiter' + company.
    """
    if li_page is None:
        return False

    try:
        # Build search keywords
        if hr_name:
            keywords = f"{hr_name} {company}" if company else hr_name
        else:
            if not company:
                print("ℹ️ No HR or company for LinkedIn search; skipping.")
                return False
            keywords = f"Recruiter {company}"

        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote(keywords)}&origin=GLOBAL_SEARCH_HEADER"
        li_page.goto(search_url, wait_until="domcontentloaded")
        try:
            li_page.wait_for_selector("a.app-aware-link", timeout=10000)
        except:
            print("⚠️ LinkedIn search results not loaded.")
            return False

        # Open first profile in results
        first_profile = li_page.locator("a.app-aware-link").first
        if first_profile.count() == 0:
            print("⚠️ No LinkedIn profiles found.")
            return False

        with li_page.context.expect_page(timeout=8000) as nw:
            first_profile.click()
        prof = nw.value
        try:
            prof.wait_for_load_state("domcontentloaded", timeout=10000)
        except:
            pass

        # Prefer Message, then Connect + Add a note
        try:
            if prof.locator("button:has-text('Message')").first.is_visible():
                prof.locator("button:has-text('Message')").first.click()
                # Type in message box
                box = prof.locator("div.msg-form__contenteditable, div[role='textbox']").first
                box.click()
                box.fill(message[:2000])  # DM can be longer
                send_btn = prof.locator("button.msg-form__send-button, button:has-text('Send')").first
                send_btn.click()
                print("📩 Sent LinkedIn message.")
                return True
        except:
            pass

        # Try Connect + Add a note (275 chars)
        try:
            conn_btn = prof.locator("button:has-text('Connect')").first
            if conn_btn.count() > 0 and conn_btn.is_enabled():
                conn_btn.click()
                try:
                    add_note_btn = prof.locator("button:has-text('Add a note')").first
                    if add_note_btn.count() == 0:
                        # Sometimes "Add a note" is an aria-label button
                        add_note_btn = prof.locator("button[aria-label*='Add a note']").first
                    add_note_btn.click(timeout=4000)
                except:
                    pass
                note_area = prof.locator("textarea[name='message'], textarea#custom-message").first
                note = linkedin_note_from_message(message)
                if note_area.count() > 0:
                    note_area.fill(note)
                    send_connect = prof.locator("button:has-text('Send'), button[aria-label='Send now']").first
                    send_connect.click()
                    print("🤝 Sent LinkedIn connect request with note.")
                    return True
        except Exception as e:
            print(f"⚠️ LinkedIn connect flow error: {e}")
            return False

    except Exception as e:
        print(f"⚠️ LinkedIn messaging failed: {e}")
        return False

    return False


# ================================
# 📌 Robust recruiter extraction
# ================================
def extract_recruiter_info(target_page):
    """
    Extract recruiter name and contact info from a job page (Naukri or external).
    Tries multiple DOM patterns and also parses JSON-LD or emails in page text.
    """
    hr_name = None
    contact_info = "N/A"

    # Try clicking any element that reveals recruiter details
    for tsel in [
        "text=View recruiter",
        "text=Recruiter Details",
        "text=Contact recruiter",
        "text=View contact",
        "text=Posted by",
        "text=Recruiter",
    ]:
        try:
            loc = target_page.locator(tsel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=1500)
                target_page.wait_for_timeout(400)
        except:
            pass

    # Common recruiter selectors/XPaths
    candidates = [
        "//span[contains(@class,'recruiter-name')]",
        "//div[contains(@class,'recruiter-details')]//*[self::span or self::a][1]",
        "xpath=//*[contains(text(),'Posted by')]/following::*[1][self::a or self::span or self::div]",
        "xpath=//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'recruiter')]/following::*[1][self::a or self::span or self::div]",
        "css=a[href*='recruiter']",
    ]
    try:
        for sel in candidates:
            loc = target_page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                text = (loc.inner_text() or "").strip()
                # Heuristics for a person name
                if text and 1 < len(text) <= 80 and "@" not in text and "http" not in text:
                    # Avoid generic labels
                    if not re.search(r"(recruiter|posted|details|contact)", text, re.I):
                        hr_name = text
                        break
    except:
        pass

    # Direct contact via links
    try:
        contact_mailto = target_page.locator("a[href^='mailto:']").first
        contact_linkedin = target_page.locator("a[href*='linkedin.com']").first
        if contact_mailto.count() > 0:
            contact_info = contact_mailto.get_attribute("href") or "N/A"
        elif contact_linkedin.count() > 0:
            contact_info = contact_linkedin.get_attribute("href") or "N/A"
    except:
        pass

    # Parse JSON-LD and page text for emails if still not found
    try:
        soup = BeautifulSoup(target_page.content(), "html.parser")
        # Look for emails in text as a last resort
        if contact_info == "N/A":
            m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", soup.get_text(" ", strip=True))
            if m:
                contact_info = f"mailto:{m.group(0)}"

        # JSON-LD parsing
        for s in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(s.get_text(strip=True))
            except:
                continue
            if isinstance(data, dict):
                datas = [data]
            elif isinstance(data, list):
                datas = data
            else:
                datas = []

            for d in datas:
                # Hiring organization or contactPoint may hold useful info
                cp = d.get("contactPoint") or []
                if isinstance(cp, dict):
                    cp = [cp]
                for c in cp:
                    if not hr_name:
                        hr_name = c.get("name") or hr_name
                    if contact_info == "N/A":
                        contact_info = c.get("email") or c.get("url") or contact_info
                # Sometimes nested recruiter info
                recr = d.get("recruiter") or d.get("agent") or {}
                if isinstance(recr, dict):
                    if not hr_name:
                        hr_name = recr.get("name") or hr_name
                    if contact_info == "N/A":
                        contact_info = recr.get("email") or recr.get("url") or contact_info
    except:
        pass

    return hr_name, contact_info


# ================================
# 📌 Apply to Job + Message Recruiter
# ================================
def try_apply_and_message(page, job, resume_text, model, li_page=None, pace_min=2, pace_max=4, use_genai=True):
    """
    Tries to apply to a job + message recruiter using Playwright.
    1. Opens job page
    2. Clicks Apply (Naukri or external)
    3. Extracts recruiter name or logs fallback info
    4. Sends Gemini-generated message if possible; else tries LinkedIn fallback
    Additionally logs jobs that require external application in a separate CSV.
    """
    job_title = job.get("title") or "Job"
    job_link = job.get("link")
    company = job.get("company")
    if not job_link:
        return False

    page.goto(job_link, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass

    applied = False
    target_page = page
    external_logged = False  # track if we already logged external apply case

    # Attempt to click 'Apply' using several robust selectors
    apply_selectors = [
        "button:has-text('Apply')",
        "a:has-text('Apply')",
        "text='Apply Now'",
        "text='Quick Apply'",
        "button[aria-label*='Apply']",
        "button[class*='apply']",
        "a[class*='apply']",
        "span:has-text('Apply')",
        "div:has-text('Apply Now')",
        "button:has-text(\"I'm interested\")",
        "button:has-text('I am interested')",
    ]

    for sel in apply_selectors:
        try:
            locator = page.locator(sel).first
            if locator.count() == 0 or not locator.is_visible():
                continue

            # A lot of Naukri apply buttons open in new tab
            try:
                with page.context.expect_page(timeout=6000) as popup_info:
                    locator.scroll_into_view_if_needed(timeout=2000)
                    locator.click(timeout=7000)
                new_page = popup_info.value
                new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                target_page = new_page
                applied = True
                print(f"✅ Applied (popup): {job_link}")

                # If the popup is not a Naukri domain, log as external application
                try:
                    new_url = (new_page.url or "").lower()
                    if new_url and "naukri.com" not in new_url:
                        log_external_application(job_title, company, job_link, new_page.url)
                        print(f"📝 Logged external application: {new_page.url}")
                        external_logged = True
                except:
                    pass
                break
            except PlaywrightTimeoutError:
                locator.scroll_into_view_if_needed(timeout=2000)
                locator.click(timeout=7000)
                try:
                    target_page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass
                applied = True
                print(f"✅ Applied: {job_link}")

                # If navigation happened to a non-Naukri domain in the same tab, log external
                try:
                    curr_url = (target_page.url or "").lower()
                    if curr_url and "naukri.com" not in curr_url:
                        log_external_application(job_title, company, job_link, target_page.url)
                        print(f"📝 Logged external application: {target_page.url}")
                        external_logged = True
                except:
                    pass
                break
        except Exception as e:
            continue

    # If still not applied, try role-based fallback selectors (tuned)
    if not applied:
        try:
            btn = page.get_by_role("button", name=re.compile(r"(apply|i.?m interested|easy apply)", re.I)).first
            if btn and btn.count() > 0 and btn.is_visible():
                try:
                    with page.context.expect_page(timeout=6000) as popup_info:
                        btn.click(timeout=7000)
                    new_page = popup_info.value
                    new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    target_page = new_page
                    applied = True
                    print(f"✅ Applied (popup via role locator): {job_link}")
                except PlaywrightTimeoutError:
                    btn.click(timeout=7000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        pass
                    target_page = page
                    applied = True
                    print(f"✅ Applied (role locator): {job_link}")
        except:
            pass

    # If the site says "Apply on company website", still treat as applied externally
    if not applied:
        try:
            cta = page.locator("text=/Apply on company/i").first
            if cta.count() > 0 and cta.is_visible():
                pre_pages = set(page.context.pages)
                cta.click()
                page.wait_for_timeout(1000)
                post_pages = set(page.context.pages)
                new_pages = list(post_pages - pre_pages)

                external_url = ""
                if new_pages:
                    try:
                        new_pages[0].wait_for_load_state("domcontentloaded", timeout=6000)
                    except:
                        pass
                    try:
                        external_url = new_pages[0].url
                    except:
                        external_url = ""
                else:
                    try:
                        external_url = page.url
                    except:
                        external_url = ""

                applied = True
                print(f"✅ Proceeding to external application: {job_link}")

                # Log as external application (regardless of capture success)
                if not external_logged:
                    log_external_application(job_title, company, job_link, external_url)
                    print(f"📝 Logged external application: {external_url or '(unknown external URL)'}")
                    external_logged = True
        except:
            pass

    if not applied:
        print("⚠️ Could not find or click Apply button.")

    # Robust recruiter extraction
    hr_name, contact_info = extract_recruiter_info(target_page)

    # If user chose not to message HR, skip messaging flows but log contacts
    if not use_genai:
        if hr_name or contact_info != "N/A":
            log_hr_contact(job_title, hr_name or "N/A", contact_info)
            print("ℹ️ Messaging disabled by user choice. Logged HR contact for manual follow-up.")
        time.sleep(random.uniform(pace_min, pace_max))
        return applied

    # Compose AI message (only if messaging enabled)
    role_hint = (target_page.title() or job_title).split("|")[0].strip()[:60]
    msg = generate_message(model, resume_text, hr_name, role_hint, job_link, company)

    # Try to send message on Naukri (if chat input exists)
    messaged_on_naukri = False
    try:
        message_box_selectors = [
            "textarea.chat-input",
            "textarea[name='message']",
            "textarea",
            "div[role='textbox']",
        ]
        for mb_sel in message_box_selectors:
            loc = target_page.locator(mb_sel).first
            if loc.count() > 0 and loc.is_enabled():
                loc.click()
                loc.fill(msg)
                for send_sel in ["button:has-text('Send')", "button[type='submit']", "text=Send"]:
                    sb = target_page.locator(send_sel).first
                    if sb.count() > 0 and sb.is_enabled():
                        sb.click()
                        print(f"📩 Messaged recruiter on Naukri: {hr_name or 'Recruiter'}")
                        messaged_on_naukri = True
                        break
            if messaged_on_naukri:
                break
    except Exception as e:
        pass

    # If messaging wasn't possible on Naukri, try LinkedIn fallback
    if not messaged_on_naukri:
        if linkedin_message_recruiter(li_page, msg, hr_name=hr_name, company=company):
            print("✅ Fallback LinkedIn messaging done.")
        else:
            # Log contact for manual follow-up
            if hr_name or contact_info != "N/A":
                log_hr_contact(job_title, hr_name or "N/A", contact_info)
                print(f"ℹ️ Logged HR contact as fallback: {hr_name or 'N/A'} | {contact_info}")
            else:
                print("ℹ️ No recruiter info available even for LinkedIn fallback.")

    # Pacing to appear human
    time.sleep(random.uniform(pace_min, pace_max))
    return applied


# ================================
# 📌 Ask user preference for messaging HR (GenAI usage)
# ================================
def ask_user_messaging_preference():
    """
    Ask user whether to send AI-generated messages to HR.
    Returns True if user says yes, else False.
    """
    try:
        ans = input("Do you want the agent to message HR with AI-generated messages? (y/N): ").strip().lower()
    except Exception:
        ans = ""
    return ans in ("y", "yes")


# ================================
# 📌 Main Run Once
# ================================
def run_once(headless=False):
    """Runs one iteration: login → discover (API/scrape) → apply → (message or LinkedIn fallback) → log."""
    cfg = load_config()
    resume_text = read_resume()

    p, browser, context, page = launch_browser(headless=headless or cfg.get("headless", False))

    # Ask the user whether to use GenAI for messaging (before scraping)
    use_genai = ask_user_messaging_preference()

    # Initialize Gemini model only if user opted in
    model = None
    if use_genai:
        model = init_gemini()

    # Prepare LinkedIn (only if messaging enabled and credentials provided)
    li_page = None
    if use_genai:
        li_page = linkedin_login(context)

    pace_min = cfg.get("apply_pacing_seconds_min", 2)
    pace_max = cfg.get("apply_pacing_seconds_max", 4)

    try:
        # Login
        naukri_email = os.getenv("naukri_email")
        naukri_password = os.getenv("naukri_password")
        if not naukri_email or not naukri_password:
            raise RuntimeError("Naukri credentials not set in .env file.")
        login(page, naukri_email, naukri_password)

        # Load already applied jobs
        applied_jobs = load_applied_jobs()

        # Discover jobs (API / hybrid / scrape) using experience strictly from config.json
        jobs = discover_jobs(page, cfg)
        print(f"🔍 Found {len(jobs)} jobs; skipping previously applied: {len(applied_jobs)}")

        # Filter out already applied
        new_jobs = [job for job in jobs if job["link"] not in applied_jobs]
        random.shuffle(new_jobs)

        # Apply to each new job
        for job in new_jobs:
            try:
                applied = try_apply_and_message(
                    page,
                    job,
                    resume_text,
                    model,
                    li_page=li_page,
                    pace_min=pace_min,
                    pace_max=pace_max,
                    use_genai=use_genai,
                )
                if applied:
                    applied_jobs.append(job["link"])
                    save_applied_jobs(applied_jobs)
                    log_applied(job["title"], job["link"])
            except Exception as e:
                print(f"❌ Job processing failed for {job['link']}: {e}")
    finally:
        try:
            if li_page:
                li_page.close()
        except:
            pass
        try:
            context.close()
        except:
            pass
        try:
            browser.close()
        except:
            pass
        try:
            p.stop()
        except:
            pass


# ================================
# 📌 Entry Point
# ================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    headless_env = (os.getenv("HEADLESS", "0") == "1")

    if mode == "loop":
        interval_min = int(os.getenv("AGENT_INTERVAL_MIN", "60"))
        while True:
            print("===== Naukri Agent tick =====")
            run_once(headless=headless_env)
            print(f"Sleeping {interval_min} minutes…")
            time.sleep(interval_min * 60)
    else:
        run_once(headless=headless_env)