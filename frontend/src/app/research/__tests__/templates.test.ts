import { describe, expect, it } from "vitest";
import {
  TEMPLATES,
  findTemplate,
  type StrategyConditionPreset,
} from "../templates";
import {
  INDICATOR_DOCS,
  INDICATOR_ORDER,
  type IndicatorKey,
} from "../indicator-docs";
import {
  applyTemplateToForm,
  formToStrategyKeys,
} from "../page";

describe("research templates", () => {
  it("ships exactly the six chips the spec asked for", () => {
    expect(TEMPLATES.map((t) => t.id)).toEqual([
      "golden_cross",
      "volume_breakout",
      "bollinger_squeeze_breakout",
      "rsi_oversold_rebound",
      "kd_golden_cross",
      "custom",
    ]);
  });

  it("every template (except custom) has at least one strategy", () => {
    for (const tpl of TEMPLATES) {
      if (tpl.id === "custom") {
        expect(tpl.strategies).toHaveLength(0);
      } else {
        expect(tpl.strategies.length).toBeGreaterThan(0);
      }
    }
  });

  it("every template has a non-empty plain-Chinese description for the tooltip", () => {
    for (const tpl of TEMPLATES) {
      expect(tpl.description.trim().length).toBeGreaterThan(0);
    }
  });

  it("every template's strategies reference a known IndicatorKey", () => {
    const known = new Set<IndicatorKey>(INDICATOR_ORDER);
    for (const tpl of TEMPLATES) {
      for (const s of tpl.strategies) {
        expect(known.has(s.indicator)).toBe(true);
      }
    }
  });

  it("findTemplate returns the right template by id and undefined for unknown", () => {
    expect(findTemplate("golden_cross")?.label).toBe("黃金交叉");
    expect(findTemplate("does_not_exist")).toBeUndefined();
  });
});

describe("applyTemplateToForm", () => {
  it("enables exactly the indicators the template lists", () => {
    const tpl = findTemplate("rsi_oversold_rebound");
    expect(tpl).toBeDefined();
    const form = applyTemplateToForm(tpl!.strategies);
    expect(form.rsi.enabled).toBe(true);
    // None of the others should be on.
    for (const key of INDICATOR_ORDER) {
      if (key === "rsi") continue;
      expect(form[key].enabled).toBe(false);
    }
  });

  it("overrides the default threshold with the template's params", () => {
    const tpl = findTemplate("bollinger_squeeze_breakout")!;
    const form = applyTemplateToForm(tpl.strategies);
    // FormState[indicator].<indicator> holds the threshold params for
    // that indicator (each slot carries all six default params for
    // shape stability — see ConditionEntry in page.tsx).
    expect(form.bollinger.bollinger.widthPct).toBe(5);
    expect(form.bollinger.bollinger.breakout).toBe("upper");
  });

  it("custom template produces an all-disabled form", () => {
    const tpl = findTemplate("custom")!;
    const form = applyTemplateToForm(tpl.strategies);
    for (const key of INDICATOR_ORDER) {
      expect(form[key].enabled).toBe(false);
    }
  });

  it("handles multi-strategy templates (golden_cross enables sma_cross + volume)", () => {
    const tpl = findTemplate("golden_cross")!;
    const form = applyTemplateToForm(tpl.strategies);
    expect(form.sma_cross.enabled).toBe(true);
    expect(form.volume.enabled).toBe(true);
    expect(form.sma_cross.sma_cross.shortPeriod).toBe(5);
    expect(form.sma_cross.sma_cross.longPeriod).toBe(20);
  });
});

describe("formToStrategyKeys", () => {
  it("filters out indicators with no backend strategy (KD, Volume today)", () => {
    const presets: StrategyConditionPreset[] = [
      { indicator: "rsi", params: { op: "<", value: 30 } },
      { indicator: "kd", params: { op: "<", level: 30 } },
      { indicator: "volume", params: { multipleOf20dAvg: 1.5 } },
    ];
    const form = applyTemplateToForm(presets);
    const keys = formToStrategyKeys(form);
    // rsi_oversold should be there, KD + Volume are skipped because
    // there is no backend strategy registered for them yet.
    expect(keys).toContain("rsi_oversold");
    expect(keys).not.toContain("kd");
    expect(keys).not.toContain("volume");
  });

  it("deduplicates when multiple indicators map to the same backend key", () => {
    // This is defensive — today no two IndicatorKeys share a backend key,
    // but the function should still dedupe if that ever changes.
    const presets: StrategyConditionPreset[] = [
      { indicator: "rsi", params: { op: "<", value: 30 } },
    ];
    const form = applyTemplateToForm(presets);
    const keys = formToStrategyKeys(form);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("returns empty when nothing is enabled", () => {
    const form = applyTemplateToForm([]);
    expect(formToStrategyKeys(form)).toEqual([]);
  });
});

describe("INDICATOR_DOCS lookup", () => {
  it("every IndicatorKey resolves to a non-empty plain-Chinese description", () => {
    for (const key of INDICATOR_ORDER) {
      const doc = INDICATOR_DOCS[key];
      expect(doc).toBeDefined();
      expect(doc.label.trim().length).toBeGreaterThan(0);
      expect(doc.description.trim().length).toBeGreaterThan(0);
    }
  });

  it("INDICATOR_ORDER matches the keys of INDICATOR_DOCS exactly", () => {
    expect(new Set(INDICATOR_ORDER)).toEqual(
      new Set(Object.keys(INDICATOR_DOCS) as IndicatorKey[]),
    );
  });

  it("at least one indicator maps to a backend strategy key", () => {
    const mapped = INDICATOR_ORDER.filter(
      (k) => INDICATOR_DOCS[k].backendStrategyKey !== null,
    );
    expect(mapped.length).toBeGreaterThan(0);
  });
});
