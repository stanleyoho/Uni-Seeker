from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel


class ConditionSchema(StrictModel):
    indicator: str
    params: dict[str, Any] = {}
    op: str
    value: Any


# --- Composable Query DSL (A2) --------------------------------------------
#
# A structured, recursive AND/OR filter. ``DslClauseSchema`` is a single
# field/cmp/value comparison; ``DslGroupSchema`` is an AND/OR group whose
# ``clauses`` may be clauses OR nested groups, giving arbitrary boolean
# trees. Both are StrictModel — typo'd keys fail loud with a 422 instead of
# silently dropping a filter. The endpoint converts the validated tree into
# the domain ``DslGroup`` dataclass and compiles it onto the screener
# engine (see ``app.modules.screener.dsl``).

# Word comparators on the wire (self-documenting, log/URL-safe). Mapped to
# symbolic ops by the compiler. "between" takes a [low, high] pair.
DslCmp = Literal["lt", "lte", "gt", "gte", "eq", "between"]


class DslClauseSchema(StrictModel):
    field: str = Field(description="Allowlisted screener field, e.g. 'RSI', 'KD_K'.")
    cmp: DslCmp
    # number for scalar comparators, [low, high] for "between". Kept as a
    # permissive union here; the compiler enforces the cmp/value pairing
    # and the field allowlist, returning a 422 on mismatch.
    value: float | list[float]


class DslGroupSchema(StrictModel):
    op: Literal["and", "or"]
    # Recursive: a member is either a leaf clause or a nested group. Clause
    # is listed first so a leaf object (which lacks ``op``/``clauses``)
    # matches it before Pydantic tries the group shape.
    clauses: list[Union["DslClauseSchema", "DslGroupSchema"]] = Field(min_length=1)


class DslScreenRequest(StrictModel):
    market: str | None = None
    filter: DslGroupSchema
    sort_by: str | None = None
    sort_order: str = "asc"
    limit: int = Field(default=50, le=500, ge=1)


class FieldMetaItem(BaseModel):
    key: str
    indicator: str
    label: str
    unit: str | None = None


class FieldMetaResponse(BaseModel):
    fields: list[FieldMetaItem]
    comparators: list[str]


class ScreenRequest(StrictModel):
    market: str | None = None
    conditions: list[ConditionSchema]
    operator: str = "AND"
    sort_by: str | None = None
    sort_order: str = "asc"
    limit: int = Field(default=50, le=500, ge=1)


class ScreenResultItem(BaseModel):
    symbol: str
    indicator_values: dict[str, float]


class ScreenResponse(BaseModel):
    results: list[ScreenResultItem]
    total: int


class IndustryScreenRequest(StrictModel):
    z_threshold: float = -1.0


class IndustryScreenResultItem(BaseModel):
    symbol: str
    name: str
    industry: str
    pe_ratio: float
    industry_avg_pe: float
    pe_z_score: float
    score: float


class IndustryScreenResponse(BaseModel):
    results: list[IndustryScreenResultItem]
    total: int
