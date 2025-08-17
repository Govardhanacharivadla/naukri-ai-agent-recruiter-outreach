# ================================
# 📌 Imports
# ================================

import os, time, json, csv, sys, random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from datetime import datetime
import pandas as pd                       # For reading/writing CSV logs
from bs4 import BeautifulSoup             # HTML parsing of job listings
from selenium import webdriver            # Browser automation
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import google.generativeai as genai       # Google Gemini API for recruiter message generation
from dotenv import load_dotenv            # Load .env API key securely


# ================================
# 📌 File Paths (constants)
# ================================
CONFIG_PATH = "config.json"              # Stores roles, locations, keywords
APPLIED_JOBS_JSON = "applied_jobs.json"  # Keeps track of already applied jobs (avoid re-applying)
APPLIED_LOG = "applied_jobs.log"         # Text log of applied jobs (title + link + timestamp)
SKIPPED_LOG = "skipped_log.csv"          # CSV log of skipped jobs (title + link + timestamp)


# ================================
# 📌 Config Loader
# ================================
def load_config():
    """Reads config.json which stores user preferences (roles, locations, keywords, pacing)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ================================
# 📌 Resume Reader
# ================================
def read_resume():
    """Reads resume text file for Gemini prompts from the path specified in .env."""
    resume_path_from_env = os.getenv("RESUME_PATH")
    if not resume_path_from_env:
        raise RuntimeError("RESUME_PATH not set in .env file.")
    with open(resume_path_from_env, "r", encoding="latin-1") as f:
        return f.read()


# ================================
# 📌 Selenium Driver Setup
# ================================
def get_driver(headless=False):
    """Initializes Chrome WebDriver with anti-detection options."""
    opts = Options()
    if headless:
        # Run browser without GUI (for servers)
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")  # reduces bot detection
    return webdriver.Chrome(service=Service(), options=opts)


# ================================
# 📌 Naukri Login Automation
# ================================
def login(driver, email, password):
    """Logs into Naukri with credentials from environment variables."""
    driver.get("https://www.naukri.com/nlogin/login")
    time.sleep(4 + random.uniform(0.5, 1.5))  # wait for page load

    driver.find_element(By.ID, "usernameField").send_keys(email)  # enter email
    driver.find_element(By.ID, "passwordField").send_keys(password)   # enter password
    driver.find_element(By.XPATH, "//button[contains(.,'Login')]").click()   # click Login button
    time.sleep(6 + random.uniform(0.5, 1.5))  # wait for login redirect


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


# ================================
# 📌 Scraper (Roles + Keywords + Location filtering)
# ================================
def scrape_jobs(driver, roles, locations, experience):
    """
    Scrapes job listings from Naukri for given roles + locations.
    Filters jobs using keywords from config.json.
    Returns a list of (title, link).
    """
    cfg = load_config()
    keywords = cfg.get("keywords", [])
    links_out = []

    for role in roles:
        for loc in locations:
            # Construct search URL dynamically (role + location + experience)
            search_url = f"https://www.naukri.com/{role.replace(' ', '-')}-jobs-in-{loc.lower()}?experience={experience}"
            driver.get(search_url)
            time.sleep(4 + random.uniform(0.3, 0.8))

            # Parse page with BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.find_all("article", {"class": "jobTuple"})  # each job card

            for card in job_cards:
                title_elem = card.find("a", {"class": "title"})
                title = title_elem.get_text(strip=True) if title_elem else ""
                link = title_elem["href"] if title_elem else None
                desc = card.get_text(" ", strip=True)

                # Match logic: if role keyword appears in title OR any keyword appears in description
                title_match = any(r.lower() in title.lower() for r in roles)
                keyword_match = any(k.lower() in desc.lower() for k in keywords)

                if link:
                    if title_match or keyword_match:
                        if link not in [l[1] for l in links_out]:
                            links_out.append((title, link))
                            print(f"📌 Match: {title}")
                    else:
                        print(f"⏩ Skipped: {title}")
                        log_skipped(title, link)

    return links_out


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
def generate_message(model, resume_text, hr_name, role_hint, job_link):
    """Generates a short recruiter message using Gemini model."""
    prompt = f"""
You are a concise, professional job applicant.
Write an 80–130 word recruiter message to {hr_name} about a role like "{role_hint}".
Use 1–2 resume achievements with metrics and end with a polite CTA.
Job: {job_link}
Resume:
{resume_text}
"""
    try:
        resp = model.generate_content(prompt)
        msg = resp.text.strip()
        return msg[:900]  # safeguard: keep under ~900 chars
    except Exception as e:
        print("Gemini generation failed:", e)
        return f"Hi {hr_name}, I noticed the opening for {role_hint}. Based on my Python/AI experience, I'd love to connect. Thanks!"


# ================================
# 📌 Apply to Job + Message Recruiter
# ================================
def try_apply_and_message(driver, job_title, job_link, resume_text, model, pace_min=2, pace_max=4):
    """
    Tries to apply to a job + message recruiter.
    1. Opens job page
    2. Clicks Apply
    3. Extracts recruiter name
    4. Sends Gemini-generated message if possible
    """
    driver.get(job_link)
    time.sleep(4 + random.uniform(0.5, 1.0))
    applied = False

    # Attempt apply button click using multiple possible XPath variations
    for xp in ["//button[contains(., 'Apply')]",
               "//a[contains(., 'Apply')]",
               "//span[contains(., 'Apply')]/ancestor::button"]:
        try:
            btn = driver.find_element(By.XPATH, xp)
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(0.5)
            btn.click()
            applied = True
            print(f"✅ Applied: {job_link}")
            break
        except:
            pass

    # Try to find recruiter name
    hr_name = None
    for xp in ["//span[contains(@class,'recruiter-name')]",
               "//div[contains(@class,'recruiter')]/descendant::span[1]",
               "//a[contains(@href,'recruiter')]/span"]:
        try:
            el = driver.find_element(By.XPATH, xp)
            txt = el.text.strip()
            if 2 <= len(txt) <= 60:  # validate recruiter name length
                hr_name = txt
                break
        except:
            continue

    # If recruiter found, send AI message
    if hr_name:
        role_hint = (driver.title or "").split("|")[0].strip()[:60]
        msg = generate_message(model, resume_text, hr_name, role_hint, job_link)

        for box_xp in ["//textarea", "//div[@contenteditable='true']", "//input[@type='text' or @type='search']"]:
            try:
                box = driver.find_element(By.XPATH, box_xp)
                driver.execute_script("arguments[0].scrollIntoView(true);", box)
                time.sleep(0.3)
                box.click()
                box.send_keys(msg)
                time.sleep(0.3)

                # Try sending message
                sent = False
                for send_xp in ["//button[contains(., 'Send')]",
                               "//span[contains(., 'Send')]/ancestor::button",
                               "//button[contains(@aria-label,'Send')]"]:
                    try:
                        sbtn = driver.find_element(By.XPATH, send_xp)
                        sbtn.click()
                        sent = True
                        break
                    except:
                        continue
                if not sent:
                    box.send_keys(Keys.RETURN)
                print(f"📩 Messaged recruiter: {hr_name}")
                break
            except:
                continue
    else:
        print("ℹ️ No recruiter name found.")

    time.sleep(random.uniform(pace_min, pace_max))
    return applied


# ================================
# 📌 Main Run Once
# ================================
def run_once(headless=False):
    """Runs one iteration: login → scrape → apply → log."""
    cfg = load_config()
    resume_text = read_resume()
    model = init_gemini()
    pace_min = cfg.get("apply_pacing_seconds_min", 2)
    pace_max = cfg.get("apply_pacing_seconds_max", 4)

    driver = get_driver(headless=headless or cfg.get("headless", False))
    try:
        # Login
        naukri_email = os.getenv("naukri_email")
        naukri_password = os.getenv("naukri_password")
        if not naukri_email or not naukri_password:
            raise RuntimeError("Naukri credentials not set in .env file.")
        login(driver, naukri_email, naukri_password)

        # Load already applied jobs
        applied_jobs = load_applied_jobs()

        # Scrape jobs
        jobs = scrape_jobs(driver, cfg["roles"], cfg["locations"], cfg.get("experience", "0"))
        print(f"🔍 Found {len(jobs)} jobs; skipping previously applied: {len(applied_jobs)}")

        # Filter out already applied
        new_jobs = [(title, link) for title, link in jobs if link not in applied_jobs]
        random.shuffle(new_jobs)  # randomize order to appear natural

        # Apply to each new job
        for title, link in new_jobs:
            try:
                applied = try_apply_and_message(driver, title, link, resume_text, model, pace_min, pace_max)
                if applied:
                    applied_jobs.append(link)  # add to memory
                    save_applied_jobs(applied_jobs)  # save to JSON
                    log_applied(title, link)  # log applied job
            except Exception as e:
                print("Job failed:", link, e)
    finally:
        driver.quit()


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