import { describe, it, expect } from "vitest";
import { classifySentiment } from "@/lib/sentiment";

describe("classifySentiment", () => {
  describe("boundary thresholds", () => {
    it("classifies exactly +1.0% as 過熱", () => {
      const r = classifySentiment(1);
      expect(r.level).toBe("过热");
      expect(r.label).toBe("過熱");
      expect(r.emoji).toBe("🔴");
      expect(r.colorClass).toBe("text-red-400");
      expect(r.arrow).toBe("▲");
    });

    it("classifies +0.99% as 上漲 (just under heated)", () => {
      const r = classifySentiment(0.99);
      expect(r.level).toBe("上涨");
      expect(r.emoji).toBe("🟠");
      expect(r.colorClass).toBe("text-orange-400");
    });

    it("classifies exactly +0.1% as 上漲", () => {
      const r = classifySentiment(0.1);
      expect(r.level).toBe("上涨");
      expect(r.arrow).toBe("▲");
    });

    it("classifies +0.09% as 平 (inside flat band)", () => {
      const r = classifySentiment(0.09);
      expect(r.level).toBe("平");
      expect(r.emoji).toBe("⚪");
    });

    it("classifies exactly 0% as 平", () => {
      const r = classifySentiment(0);
      expect(r.level).toBe("平");
      expect(r.label).toBe("平");
      expect(r.emoji).toBe("⚪");
      expect(r.colorClass).toBe("text-gray-400");
      expect(r.arrow).toBe("—");
    });

    it("classifies -0.09% as 平 (inside flat band, negative side)", () => {
      const r = classifySentiment(-0.09);
      expect(r.level).toBe("平");
    });

    it("classifies exactly -0.1% as 下跌", () => {
      const r = classifySentiment(-0.1);
      expect(r.level).toBe("下跌");
      expect(r.emoji).toBe("🔵");
      expect(r.colorClass).toBe("text-sky-400");
      expect(r.arrow).toBe("▼");
    });

    it("classifies -0.99% as 下跌 (just above deep drop)", () => {
      const r = classifySentiment(-0.99);
      expect(r.level).toBe("下跌");
    });

    it("classifies exactly -1.0% as 深跌", () => {
      const r = classifySentiment(-1);
      expect(r.level).toBe("深跌");
      expect(r.label).toBe("深跌");
      expect(r.emoji).toBe("🟣");
      expect(r.colorClass).toBe("text-purple-400");
      expect(r.arrow).toBe("▼");
    });

    it("classifies -5% as 深跌", () => {
      expect(classifySentiment(-5).level).toBe("深跌");
    });

    it("classifies +5% as 過熱", () => {
      expect(classifySentiment(5).level).toBe("过热");
    });
  });

  describe("invalid / missing inputs collapse to 平", () => {
    it("handles NaN", () => {
      const r = classifySentiment(NaN);
      expect(r.level).toBe("平");
      expect(r.arrow).toBe("—");
    });

    it("handles undefined", () => {
      const r = classifySentiment(undefined);
      expect(r.level).toBe("平");
    });

    it("handles null", () => {
      const r = classifySentiment(null);
      expect(r.level).toBe("平");
    });

    it("handles empty string", () => {
      const r = classifySentiment("");
      expect(r.level).toBe("平");
    });

    it("handles non-numeric string", () => {
      const r = classifySentiment("not-a-number");
      expect(r.level).toBe("平");
    });

    it("handles Infinity by collapsing to 平", () => {
      expect(classifySentiment(Infinity).level).toBe("平");
      expect(classifySentiment(-Infinity).level).toBe("平");
    });
  });

  describe("string inputs (Decimal-as-string contract)", () => {
    it("parses '+1.5' as 過熱", () => {
      expect(classifySentiment("1.5").level).toBe("过热");
    });

    it("parses '-0.5' as 下跌", () => {
      expect(classifySentiment("-0.5").level).toBe("下跌");
    });

    it("parses '0.00' as 平", () => {
      expect(classifySentiment("0.00").level).toBe("平");
    });
  });
});
