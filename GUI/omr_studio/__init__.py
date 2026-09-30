"""OMR Studio - desktop front end for the OMRChecker engine."""
import sys
from pathlib import Path

# The engine (``src`` package) lives at the repository root; make it importable
# regardless of the directory the application is launched from.
_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

__version__ = "1.0.0"
APP_NAME = "OMR Studio"

from .compat import install_monitor_fallback  # noqa: E402

install_monitor_fallback()
