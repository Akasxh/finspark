"""
Minimal conftest for unit tests — does NOT depend on the finspark app package.
Imports only from app.integrations which is importable via PYTHONPATH=backend/.
"""

import sys
from pathlib import Path

# Ensure backend/ is on path so `app.*` imports resolve
_BACKEND = Path(__file__).parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
