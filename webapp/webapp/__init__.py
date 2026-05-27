"""ECM Reflex web app."""

import os
import sys

# Make the sibling `pythonlib/` package importable without requiring `pip install -e`.
_PYTHONLIB = os.path.join(os.path.dirname(__file__), "..", "..", "pythonlib")
if _PYTHONLIB not in sys.path:
    sys.path.insert(0, _PYTHONLIB)
