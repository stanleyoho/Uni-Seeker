"""B6d — import-linter layering contracts must stay green.

Runs ``lint-imports`` (the same command CI runs) as a subprocess from the
backend root so the ``[tool.importlinter]`` config in ``pyproject.toml`` is
discovered exactly as it is in CI. Asserting exit code 0 means every declared
contract is KEPT — a future reverse-layer import will fail this test locally
before it ever reaches CI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    shutil.which("lint-imports") is None,
    reason="import-linter not installed (dev dependency)",
)
def test_import_linter_contracts_pass() -> None:
    result = subprocess.run(
        ["lint-imports"],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"import-linter reported a broken layering contract:\n{result.stdout}\n{result.stderr}"
    )
    assert "Contracts:" in result.stdout
    assert "broken" not in result.stdout.split("Contracts:")[-1].lower() or (
        "0 broken" in result.stdout
    )
