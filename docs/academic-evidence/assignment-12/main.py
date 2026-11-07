"""
main.py
=======
Entry point for the UniMatch REST API.

Run with:
    uvicorn main:app --reload

Or directly:
    python main.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from api import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
