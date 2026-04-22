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
        conditions=req.conditions,
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
