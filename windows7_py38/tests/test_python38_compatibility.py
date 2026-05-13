from __future__ import annotations

import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_sources_compile_on_current_interpreter() -> None:
    for path in PROJECT_ROOT.glob("*.py"):
        py_compile.compile(str(path), doraise=True)
