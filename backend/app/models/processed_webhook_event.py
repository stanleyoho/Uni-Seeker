from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedWebhookEvent(Base):
    """Idempotency log for incoming Stripe (and other provider) webhooks.

    Stripe delivers webhooks at-least-once. We insert ``event_id`` with
    ``ON CONFLICT DO NOTHING`` to ensure each event's side effects only
    run once even when re-delivered.
    """

    __tablename__ = "processed_webhook_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="stripe", default="stripe"
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )
    event_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
