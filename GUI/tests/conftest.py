import sys
from pathlib import Path

import pytest

GUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_DIR))

from omr_studio.paths import ENGINE_ROOT, Workspace  # noqa: E402
from omr_studio.services.templates import TemplateLibrary  # noqa: E402


@pytest.fixture()
def workspace(tmp_path):
    return Workspace(tmp_path / "ws").ensure()


@pytest.fixture()
def library(workspace):
    return TemplateLibrary(workspace.templates)


@pytest.fixture()
def samples():
    return ENGINE_ROOT / "samples"
