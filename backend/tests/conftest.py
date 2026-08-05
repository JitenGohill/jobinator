import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    def load(name: str) -> Any:
        return json.loads((Path(__file__).parent / "fixtures" / name).read_text())

    return load
