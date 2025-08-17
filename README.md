# Naukri AI Agent (Gemini Free Tier)

1) Logs in to Naukri
2) Searches roles (Python Developer, AI Engineer, SDE1) in Hyderabad & Bangalore
3) Applies automatically
4) Finds recruiter (if visible)
5) Drafts & sends a personalized message using Gemini free tier
6) Logs applied jobs

## Setup
pip install -r requirements.txt
Create .env with GEMINI_API_KEY
Edit config.json with your Naukri credentials

## Run
python agent.py
HEADLESS=1 python agent.py
