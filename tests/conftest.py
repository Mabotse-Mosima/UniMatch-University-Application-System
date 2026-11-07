"""Pytest root conftest — ensures src/ is on the Python path."""

import sys
from pathlib import Path

# src/ is the package root; required for `from unimatch.xxx import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
