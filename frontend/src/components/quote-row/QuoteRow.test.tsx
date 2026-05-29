// QuoteRow contract tests.
//
// We focus on the rendering contract the user actually cares about:
//   symbol + name + price + absolute change + percent change all visible.
// Visual styling (colours, layout) is left to manual screenshot review.

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QuoteRow } from "./QuoteRow";

describe("QuoteRow", () => {
  it("renders symbol, name, price, abs change, percent change", () => {
    render(
      <QuoteRow
        symbol="2330.TW"
        name="台積電"
        price="1100.50"
        change="12.50"
        changePercent="1.15"
        market="TW_TWSE"
      />,
    );
    // TW suffix stripped for display
    expect(screen.getByText("2330")).toBeInTheDocument();
    expect(screen.getByText("台積電")).toBeInTheDocument();
    expect(screen.getByText("1,100.50")).toBeInTheDocument();
    // abs change + percent rendered together on the right side
    expect(screen.getByText("+12.50 (+1.15%)")).toBeInTheDocument();
  });

  it("derives absolute change from price × percent when missing", () => {
    render(
      <QuoteRow
        symbol="0050.TW"
        name="元大台灣50"
        price="150.00"
        // no `change` prop — derived value should be 150 * 2 / 100 = 3.00
        changePercent="2"
      />,
    );
    expect(screen.getByText("+3.00 (+2.00%)")).toBeInTheDocument();
  });

  it("renders em-dash for missing fields (search / scanner gap)", () => {
    render(
      <QuoteRow
        symbol="2454.TW"
        name="聯發科"
        // price/change/percent absent — search result API gap
      />,
    );
    // dashes appear for price and combined change line
    const dashes = screen.getAllByText(/—/);
    // at least price (1) + abs+pct combo (1) = 2 dashes
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("compact variant still shows every field on a single line", () => {
    render(
      <QuoteRow
        variant="compact"
        symbol="AAPL"
        name="Apple Inc."
        price="195.00"
        change="-2.50"
        changePercent="-1.27"
      />,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("195.00")).toBeInTheDocument();
    expect(screen.getByText("-2.50")).toBeInTheDocument();
    expect(screen.getByText("-1.27%")).toBeInTheDocument();
  });

  it("wraps in a Link when href is provided", () => {
    const { container } = render(
      <QuoteRow
        symbol="MSFT"
        name="Microsoft"
        price="420.00"
        changePercent="0.5"
        href="/stocks/MSFT"
      />,
    );
    const anchor = container.querySelector('a[href="/stocks/MSFT"]');
    expect(anchor).not.toBeNull();
  });

  it("renders a button when only onClick is provided", () => {
    const { container } = render(
      <QuoteRow
        symbol="2454.TW"
        name="聯發科"
        price="1245"
        changePercent="12.74"
        onClick={() => {}}
      />,
    );
    expect(container.querySelector("button")).not.toBeNull();
  });
});
