import os
from pathlib import Path

import pytest

from backend.app.services.case_service import CaseService


# Application tests need a fresh isolated repository for every app instance;
# the product default is persistent SQLite for local Arena use.
os.environ["ARENA_REPOSITORY"] = "memory"


@pytest.fixture(scope="session")
def cases() -> CaseService:
    manifest = Path("data/manifests/mvp50_manifest.json")
    if not manifest.exists():
        pytest.fail("Run `make preprocess-ddxplus` before tests")
    return CaseService()
