import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest

from best_case.config import Config


@pytest.fixture(scope="session")
def settings_file():
    return ROOT / "config" / "settings.yaml"


@pytest.fixture()
def cfg(settings_file):
    return Config.load(settings_file)
