from app.modules.backtester.grid_search import (
    GridSearchConfig,
    GridSearchResultItem,
    compute_composite_scores,
)


def test_config_total_combinations():
    config = GridSearchConfig(
        strategy_keys=["rsi_oversold"],
        param_grid={"rsi_buy": [25, 30, 35], "rsi_sell": [65, 70]},
    )
    assert config.total_combinations() == 6


def test_config_empty_grid():
    config = GridSearchConfig(strategy_keys=["rsi_oversold"], param_grid={})
    assert config.total_combinations() == 1


def test_composite_scores_filters_low_trades():
    items = [
        GridSearchResultItem(
            name="few",
            params={},
            total_return=100,
            annualized_return=50,
            max_drawdown=-10,
            win_rate=80,
            total_trades=2,
            profit_factor=5,
            sharpe=1.5,
            wins=2,
            losses=0,
        ),
        GridSearchResultItem(
            name="many",
            params={},
            total_return=50,
            annualized_return=30,
            max_drawdown=-15,
            win_rate=60,
            total_trades=20,
            profit_factor=2,
            sharpe=0.8,
            wins=12,
            losses=8,
        ),
    ]
    scored = compute_composite_scores(items, min_trades=6, min_win_rate=50)
    assert len(scored) == 1
    assert scored[0][1].name == "many"


def test_composite_scores_empty():
    scored = compute_composite_scores([])
    assert scored == []
