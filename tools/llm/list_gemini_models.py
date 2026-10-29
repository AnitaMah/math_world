"""
One-off helper: list the Gemini models your API key actually has access
to, and which ones support generateContent (i.e. can be used as
GEMINI_MODEL). Run this once to pick a real model name instead of
guessing from docs/blogs that may be ahead of or behind what's live.

Usage:
    python scripts/list_gemini_models.py
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not set (check your .env file).")

client = genai.Client(api_key=api_key)

print("Models supporting generateContent:\n")
for model in client.models.list():
    actions = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None) or []
    if any("generateContent" in str(a) for a in actions) or not actions:
        print(f"  {model.name}")
