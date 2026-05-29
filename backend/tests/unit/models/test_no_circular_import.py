"""Regression test for the cross-package circular import.

Seed-style entry points (``scripts/seed_e2e_data.py``) import ``app.db.models``
*before* ``app.models``. That order used to trip a circular import because
``app.models.__init__`` re-imported names from ``app.db.models.alerts`` while
``alerts`` was still mid-load (one of its submodules was running
``from app.models.base import Base`` which forced ``app.models.__init__`` to
execute).

This test runs the failing chain inside an isolated subprocess so pytest's
module cache cannot mask the bug, and asserts the registration side effects
still produced the expected tables on ``Base.metadata``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# backend/tests/unit/models/test_no_circular_import.py -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=_BACKEND_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_seed_style_import_chain_does_not_raise() -> None:
    """The exact sequence seed_e2e_data.py:54 uses must not ImportError."""
    script = "import app.db.models\nprint('OK')"
    result = _run_isolated(script)
    assert result.returncode == 0, (
        f"seed-style import chain failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK" in result.stdout


def test_cross_package_registration_still_works() -> None:
    """After fixing the cycle, side-effect-only imports MUST still register
    alert_rules + f13_filings + portfolio_accounts on Base.metadata.
    """
    script = (
        "import app.db.models\n"
        "from app.models.base import Base\n"
        "names = set(Base.metadata.tables.keys())\n"
        "missing = [t for t in ['alert_rules', 'f13_filings', 'portfolio_accounts'] if t not in names]\n"
        "assert not missing, f'missing tables on Base.metadata: {missing}'\n"
        "print('OK', len(names))\n"
    )
    result = _run_isolated(script)
    assert result.returncode == 0, (
        f"registration regression:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK" in result.stdout


def test_legacy_then_db_models_order_also_works() -> None:
    """Reverse import order — load app.models first, then app.db.models.
    Both directions must succeed so any callsite remains safe.
    """
    script = "import app.models  # noqa: F401\nimport app.db.models  # noqa: F401\nprint('OK')\n"
    result = _run_isolated(script)
    assert result.returncode == 0, (
        f"reverse import order failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK" in result.stdout
