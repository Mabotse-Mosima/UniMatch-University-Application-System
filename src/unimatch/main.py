"""
unimatch/main.py
=================
Entry point for the UniMatch REST API.

Run with:
    uvicorn unimatch.main:app --reload

Or directly:
    python -m unimatch.main
"""

from dotenv import load_dotenv
load_dotenv()

from unimatch.api import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("unimatch.main:app", host="0.0.0.0", port=8000, reload=True)
