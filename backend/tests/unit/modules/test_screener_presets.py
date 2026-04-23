from app.modules.screener.presets import PRESETS


def test_all_presets_have_required_fields() -> None:
    for key, preset in PRESETS.items():
        assert preset.key == key
        assert preset.name_zh
        assert preset.name_en
        assert preset.description_zh
        assert preset.description_en
        assert preset.conditions.rules


def test_preset_count() -> None:
    assert len(PRESETS) >= 5


def test_oversold_bounce_preset() -> None:
    p = PRESETS["oversold_bounce"]
    assert p.conditions.operator == "AND"
    assert len(p.conditions.rules) >= 2
    assert p.sort_by == "RSI"
