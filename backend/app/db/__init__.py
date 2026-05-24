"""Portfolio Tracker DB layer (per design doc §5.5).

This package hosts ORM models for the Portfolio Tracker module under
`app/db/models/portfolio/`. The existing `app/models/` namespace is kept
intact for the legacy trade-journal and other modules. Both packages
share the same `Base` declarative metadata (re-imported from
`app.models.base`), so Alembic autodetect via `app/models/__init__.py`
sees portfolio tables once they are imported there.
"""
