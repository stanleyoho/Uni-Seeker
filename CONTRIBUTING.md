# Contributing to Uni-Seeker

This document describes the development standards, workflow, and requirements for contributing to the Uni-Seeker stock analysis platform.

## Code Standards

### Python (Backend)

- **Linter / Formatter**: [ruff](https://docs.astral.sh/ruff/) -- enforces formatting and lint rules in a single tool.
- **Type checking**: `mypy --strict` -- every function must have complete type annotations.
- **Type hints required**: All function signatures, return types, and non-trivial variables must be annotated. Use `float | None` union syntax (not `Optional`).
- **Dataclasses**: Prefer `@dataclass(frozen=True)` for value objects. Use Pydantic `BaseModel` only in the API schema layer.

### TypeScript (Frontend)

- **Strict mode**: `tsconfig.json` must set `"strict": true`.
- **No `any`**: The `any` type is prohibited. Use `unknown` and narrow with type guards when the type is genuinely uncertain.
- **Component conventions**: React components use named exports, PascalCase filenames, and co-located test files.

### Test-Driven Development (TDD)

TDD is mandatory for all feature and bug-fix work. The cycle is:

1. **Red** -- Write a failing test that describes the expected behavior.
2. **Green** -- Write the minimum code to make the test pass.
3. **Refactor** -- Clean up while keeping tests green.

Every pull request must include tests that were written _before_ the implementation.

### Pre-commit Hooks

The project uses [pre-commit](https://pre-commit.com/) to enforce quality gates automatically.

| Hook stage | Tool | Purpose |
|------------|------|---------|
| `pre-commit` | ruff (format + lint) | Catch style and lint issues before commit |
| `pre-commit` | mypy --strict | Catch type errors before commit |
| `pre-push` | pytest | Run the full test suite before pushing |

Install hooks after cloning:

```bash
cd backend
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push
```

### Code Coverage

| Threshold | Requirement |
|-----------|-------------|
| Minimum   | 85% -- PRs that drop coverage below this are blocked |
| Target    | 90%+ -- aim for this on every module |

Check coverage locally:

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

---

## Module Development Workflow

Follow these six steps whenever you add or modify a module (indicator, model, provider, etc.).

### 1. Write the Specification Document

Before writing any code, create a specification using the appropriate template in `docs/templates/`:

- **Indicator** -- use `docs/templates/indicator-spec.md`
- **Valuation / prediction model** -- use `docs/templates/model-spec.md`

The spec defines the formula, parameters, expected behavior, and edge cases. It is reviewed alongside the code.

### 2. Write Failing Tests

Translate the spec's test cases into pytest tests. Place test files in `backend/tests/` mirroring the source layout:

```
backend/app/modules/indicators/rsi.py
backend/tests/modules/indicators/test_rsi.py
```

Run the tests and confirm they fail:

```bash
pytest tests/modules/indicators/test_rsi.py -v
```

### 3. Implement

Write the implementation to make the tests pass. Follow the existing patterns:

- Indicators implement the `Indicator` protocol and return `IndicatorResult`.
- Price estimators return `ValuationEstimate`.
- Financial analysis modules operate on `FinancialData` / `FinancialRatios`.

### 4. Pass All Quality Gates

```bash
ruff check app/
ruff format --check app/
mypy --strict app/
pytest --cov=app --cov-report=term-missing
```

All four commands must succeed with zero errors.

### 5. Update Module Documentation

Update or create the corresponding doc in `docs/indicators/` or `docs/models/`. The documentation is part of the deliverable -- incomplete docs block the PR.

### 6. Commit with Conventional Commits

See the commit message format below.

---

## Conventional Commits

Every commit message must follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <short description>

[optional body]

[optional footer]
```

### Allowed Types

| Type | When to use |
|------|-------------|
| `feat:` | A new user-facing feature or capability |
| `fix:` | A bug fix |
| `docs:` | Documentation-only changes |
| `test:` | Adding or updating tests (no production code change) |
| `refactor:` | Code restructuring with no behavior change |
| `infra:` | CI/CD, Docker, deployment, tooling changes |

### Examples

```
feat: add RSI indicator with configurable period

Implements the Wilder smoothing method. Includes edge-case handling
for flat price series (all gains or all losses).

fix: correct MACD signal line offset calculation

The signal EMA was being applied from index 0 instead of from
the first valid MACD value, producing incorrect early values.

docs: add Bollinger Bands indicator specification
```

### Scope (Optional)

You may add a scope in parentheses to narrow the context:

```
feat(indicators): add KD stochastic oscillator
fix(dcf): handle zero shares outstanding
```

---

## Pull Request Requirements

A PR is ready for review when all of the following are true:

- [ ] **All tests pass** -- `pytest` exits with code 0.
- [ ] **Coverage not decreased** -- The overall coverage percentage is equal to or higher than the base branch.
- [ ] **Linting and type checks pass** -- `ruff check`, `ruff format --check`, and `mypy --strict` all pass.
- [ ] **Module documentation updated** -- New or changed modules have corresponding docs in `docs/`.
- [ ] **Conventional commit messages** -- Every commit in the PR follows the format above.
- [ ] **Reviewed by at least one person** -- At least one approving review from a team member.

### PR Title

Use the same conventional commit format for the PR title:

```
feat(indicators): add KD stochastic oscillator
```

### PR Description

Include:

1. **What** -- A brief summary of the change.
2. **Why** -- The motivation or issue being addressed.
3. **How to test** -- Steps a reviewer can follow to verify the change.
4. **Related docs** -- Links to any new or updated spec documents.

---

## Project Structure Reference

```
backend/
  app/
    api/v1/           # FastAPI route handlers
    models/            # SQLAlchemy ORM models
    modules/
      indicators/      # Technical indicators (RSI, MACD, KD, MA, BB, Volume)
      price_estimator/  # Valuation models (PE, DDM, DCF, Composite)
      financial_analysis/  # Ratios and health scoring
      price_updater/   # Market data providers (TWSE, TPEx, yfinance)
      screener/        # Stock screening engine
      notifier/        # Notification system (Telegram)
      backtester/      # Backtesting engine
      strategy/        # Trading strategy definitions
      valuation/       # Valuation data providers (TWSE BWIBBU)
    schemas/           # Pydantic request/response schemas
    services/          # Business logic services
  tests/               # Test files (mirrors app/ structure)
frontend/              # Next.js frontend application
docs/
  templates/           # Specification templates
  indicators/          # Indicator documentation
  models/              # Valuation model documentation
```

---

## TW Stock Notes (台股備註)

When working with Taiwan Stock Exchange (TWSE / 證交所) or TPEx (櫃買中心) data:

- Stock symbols use the `.TW` suffix for TWSE-listed stocks and `.TWO` for TPEx (OTC) stocks.
- TWSE APIs return field names like `PEratio`, `PBratio`, `DividendYield` -- map these carefully in provider code.
- Trading sessions are 09:00-13:30 TST (UTC+8). Data availability may lag by 15-30 minutes after market close.
- Financial statements follow ROC calendar in some TWSE endpoints (民國年). Convert to Gregorian dates in the provider layer, never in business logic.
