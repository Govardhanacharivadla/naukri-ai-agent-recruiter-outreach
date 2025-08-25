# Naukri AI Agent (Hybrid,Gemini Free Tier)

This a sophisticated job application agent that automates the process of finding and applying for jobs on Naukri. It uses a hybrid approach to job discovery, applies with robust logic, and leverages the Gemini API for personalized recruiter outreach.

---

### Key Features 🚀
* **Hybrid Job Discovery:** Finds jobs by combining direct scraping of Naukri with searches via the JSearch and Adzuna APIs for a wider, more reliable set of results.
* **Smart Application Logic:**
    * Finds and clicks a variety of "Apply" buttons.
    * Detects jobs that require an external application on a company website.
    * Logs external application links to a separate CSV file for manual follow-up.
* **Automated Messaging:**
    * Drafts personalized recruiter messages using your resume and the Gemini API.
    * Performs a **LinkedIn fallback** to message a recruiter if contact details aren't found on the job page.
* **Comprehensive Logging:** Tracks applied jobs, skipped jobs, and HR contact information to keep a complete record of all activity.

---

### Setup ⚙️
1. **Create and Activate a Virtual Environment:**
    This ensures all project dependencies are isolated and do not conflict with other Python projects on your machine.

    **On macOS and Linux:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    **On Windows:**
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```

2.  **Install Dependencies:** First, clone the repository, then install all required libraries using `pip`.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install Browser Binaries:** This is a crucial step for Playwright.
    ```bash
    playwright install
    ```

4.  **Create `.env` File:** Create a file named `.env` in the root directory and add all your credentials. The script reads these to operate.
    ```ini
    # Naukri Credentials
    NAUKRI_EMAIL="your_naukri_email"
    NAUKRI_PASSWORD="your_naukri_password"

    # Gemini API Key
    GEMINI_API_KEY="your_gemini_key"

    # LinkedIn Credentials (Optional for messaging fallback)
    LINKEDIN_EMAIL="your_linkedin_email"
    LINKEDIN_PASSWORD="your_linkedin_password"

    # API Keys for Job Discovery (Optional)
    ADZUNA_APP_ID="your_adzuna_id"
    ADZUNA_APP_KEY="your_adzuna_key"
    RAPIDAPI_KEY="your_rapidapi_key"

    # Resume Path (PDF format)
    RESUME_PATH="/path/to/your/resume.pdf"
    ```

5.  **Edit `config.json`:**
    * Modify `roles`, `locations`, `experience`, and `keywords` to match your preferences.
    * Adjust `apply_pacing` to control the time between each application.
    * Set the `discovery` mode to `scrape`, `api`, or `hybrid`.

---

### Usage ▶️

You can run the agent in two modes:

* **Single Run:** Runs through the job search and application process once, then exits.
    ```bash
    python agent.py
    ```

* **Continuous Loop:** Runs continuously, checking for new jobs every `AGENT_INTERVAL_MIN` (default 60 minutes) as defined in your environment variables.
    ```bash
    python agent.py --loop
    ```

To run in **headless mode** (without a visible browser), set the `HEADLESS` environment variable:
```bash
HEADLESS=1 python agent.py
```
---

### Logs and Outputs 📝

The agent creates several files to track its activity and provide a record of your job applications:
* `applied_jobs.log`: A human-readable list of all jobs the agent successfully applied to.
* `skipped_log.csv`: A CSV file of jobs skipped due to keyword or experience mismatches.
* `hr_contact_log.txt`: A log of HR contact information for jobs where a direct message couldn't be sent.
* `external_apply_log.csv`: A CSV file of jobs that require you to complete the application on an external website.