"""Expose archived packages only when explicitly running the legacy test suite."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))