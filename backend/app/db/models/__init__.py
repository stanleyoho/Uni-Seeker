"""ORM models for the new Portfolio Tracker module (design doc §5.5)."""

# Eager-import sibling model packages so SQLAlchemy mapper configuration
# sees every Base subclass before any cross-package relationship resolves.
from app.db.models import alerts as _alerts
