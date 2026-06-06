"""K3a — alembic migration DAG sanity.

Guards the migration chain against the failure mode E2E-2 hit: the DAG must
have exactly ONE head, otherwise ``alembic upgrade head`` aborts with
"Multiple head revisions are present". This runs in the regular (sqlite) CI
suite — it inspects the migration *scripts*, not a live DB — so a future PR
that forks the chain into two heads fails here immediately.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_migration_chain_has_single_head() -> None:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, (
        f"Expected exactly one alembic head, found {len(heads)}: {heads}. "
        "Add a merge revision (alembic merge -m '...' <head1> <head2>)."
    )


def test_migration_chain_has_single_base() -> None:
    """A clean linear-rooted chain has exactly one base (down_revision=None)."""
    bases = _script_directory().get_bases()
    assert len(bases) == 1, f"Expected exactly one alembic base, found {len(bases)}: {bases}"
