"""Root conftest — adds the project root to sys.path so that ``unimatch``,
``repositories``, ``factories``, and ``tests`` are all importable without
installing the package.
"""
import sys
from pathlib import Path

# Insert project root at position 0 so local packages shadow any installed ones
sys.path.insert(0, str(Path(__file__).parent))
