import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.notification import NotificationRule
from app.schemas.notification import (
    NotificationRuleCreate,
    NotificationRuleListResponse,
    NotificationRuleResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/channels")
def list_channels() -> list[dict]:
    """List available notification channels and their status."""
    return [
        {
            "id": "telegram",
            "name_zh": "Telegram",
            "name_en": "Telegram",
            "status": "available",
            "description_zh": "透過 Telegram Bot 即時推播通知",
            "description_en": "Real-time push notifications via Telegram Bot",
            "setup_required": True,
            "setup_fields": ["bot_token", "chat_id"],
        },
        {
            "id": "email",
            "name_zh": "Email",
            "name_en": "Email",
            "status": "coming_soon",
            "description_zh": "電子郵件通知（即將推出）",
            "description_en": "Email notifications (coming soon)",
        },
        {
            "id": "line",
            "name_zh": "LINE Notify",
            "name_en": "LINE Notify",
            "status": "coming_soon",
            "description_zh": "LINE 通知（即將推出）",
            "description_en": "LINE Notify (coming soon)",
        },
        {
            "id": "webhook",
            "name_zh": "Webhook",
            "name_en": "Webhook",
            "status": "coming_soon",
            "description_zh": "自訂 Webhook（即將推出）",
            "description_en": "Custom Webhook (coming soon)",
        },
    ]


@router.get("/templates")
def list_notification_templates() -> list[dict]:
    """List preset notification templates."""
    return [
        {
            "key": "price_above",
            "name_zh": "股價突破通知",
            "name_en": "Price Breakout Alert",
            "description_zh": "當股價突破指定價位時通知",
            "description_en": "Alert when price breaks above target",
            "rule_type": "price_alert",
            "default_conditions": [{"indicator": "price", "operator": ">=", "value": 0}],
        },
        {
            "key": "rsi_oversold",
            "name_zh": "RSI 超賣通知",
            "name_en": "RSI Oversold Alert",
            "description_zh": "RSI 低於 30 時通知，可能有反彈機會",
            "description_en": "Alert when RSI drops below 30",
            "rule_type": "indicator_alert",
            "default_conditions": [{"indicator": "RSI", "operator": "<", "value": 30, "params": {"period": 14}}],
        },
        {
            "key": "daily_summary",
            "name_zh": "每日盤後摘要",
            "name_en": "Daily Post-Market Summary",
            "description_zh": "每日收盤後自動發送持股表現與篩選結果",
            "description_en": "Daily summary of holdings and screener results after market close",
            "rule_type": "daily_summary",
            "default_conditions": [],
        },
        {
            "key": "big_move",
            "name_zh": "大幅波動警示",
            "name_en": "Big Move Alert",
            "description_zh": "單日漲跌幅超過 5% 時通知",
            "description_en": "Alert when daily change exceeds ±5%",
            "rule_type": "price_alert",
            "default_conditions": [{"indicator": "change_percent", "operator": ">=", "value": 5}],
        },
        {
            "key": "multi_indicator",
            "name_zh": "多指標組合通知",
            "name_en": "Multi-Indicator Alert",
            "description_zh": "自訂多個指標條件組合觸發通知",
            "description_en": "Custom multi-indicator condition alert",
            "rule_type": "multi_condition",
            "default_conditions": [
                {"indicator": "RSI", "operator": "<", "value": 35, "params": {"period": 14}},
                {"indicator": "KD_K", "operator": "<", "value": 25},
            ],
        },
    ]


@router.get("/rules", response_model=NotificationRuleListResponse)
async def list_rules(
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleListResponse:
    query = select(NotificationRule).where(NotificationRule.is_active.is_(True))
    result = await db.execute(query)
    rules = list(result.scalars().all())

    return NotificationRuleListResponse(
        rules=[NotificationRuleResponse.model_validate(r) for r in rules],
        total=len(rules),
    )


@router.post("/rules", response_model=NotificationRuleResponse, status_code=201)
async def create_rule(
    req: NotificationRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleResponse:
    rule = NotificationRule(
        name=req.name,
        rule_type=req.rule_type,
        symbol=req.symbol,
        conditions=[c.model_dump() for c in req.conditions],
        condition_logic=req.condition_logic,
        channels=json.dumps(req.channels),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return NotificationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    query = select(NotificationRule).where(NotificationRule.id == rule_id)
    result = await db.execute(query)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = False
    await db.commit()
