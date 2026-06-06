import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  DslFilterBuilder,
  builderToFilter,
  countClauses,
  makeClause,
  makeGroup,
  type BuilderGroup,
} from "../dsl-filter-builder";
import type { DslFieldMeta } from "@/lib/api-client";

const FIELDS: DslFieldMeta[] = [
  { key: "RSI", indicator: "RSI", label: "RSI (14)", unit: null },
  { key: "KD_K", indicator: "KD", label: "KD %K", unit: null },
  { key: "BIAS", indicator: "BIAS", label: "Bias %", unit: "pct" },
];

describe("builderToFilter (pure)", () => {
  it("maps a flat group to the API payload shape", () => {
    const group: BuilderGroup = {
      kind: "group",
      op: "and",
      children: [
        { kind: "clause", field: "RSI", cmp: "lt", value: 30 },
        { kind: "clause", field: "KD_K", cmp: "gt", value: 50 },
      ],
    };
    expect(builderToFilter(group)).toEqual({
      op: "and",
      clauses: [
        { field: "RSI", cmp: "lt", value: 30 },
        { field: "KD_K", cmp: "gt", value: 50 },
      ],
    });
  });

  it("preserves nested AND/OR groups", () => {
    const group: BuilderGroup = {
      kind: "group",
      op: "and",
      children: [
        { kind: "clause", field: "RSI", cmp: "lt", value: 30 },
        {
          kind: "group",
          op: "or",
          children: [
            { kind: "clause", field: "KD_K", cmp: "lt", value: 20 },
            { kind: "clause", field: "BIAS", cmp: "lt", value: -5 },
          ],
        },
      ],
    };
    const filter = builderToFilter(group);
    expect(filter.op).toBe("and");
    expect(filter.clauses).toHaveLength(2);
    expect(filter.clauses[1]).toEqual({
      op: "or",
      clauses: [
        { field: "KD_K", cmp: "lt", value: 20 },
        { field: "BIAS", cmp: "lt", value: -5 },
      ],
    });
    expect(countClauses(group)).toBe(3);
  });
});

describe("<DslFilterBuilder />", () => {
  it("renders existing clause rows from the group prop", () => {
    const group: BuilderGroup = {
      kind: "group",
      op: "and",
      children: [makeClause("RSI")],
    };
    render(<DslFilterBuilder group={group} onChange={() => {}} fields={FIELDS} />);
    expect(screen.getAllByTestId("dsl-clause-row")).toHaveLength(1);
    expect(screen.getByLabelText("Field")).toBeInTheDocument();
  });

  it("adds a condition when '+ Condition' is clicked", () => {
    const onChange = vi.fn();
    const group = makeGroup("and");
    render(<DslFilterBuilder group={group} onChange={onChange} fields={FIELDS} />);

    fireEvent.click(screen.getByText("+ Condition"));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as BuilderGroup;
    expect(next.children).toHaveLength(1);
    expect(next.children[0].kind).toBe("clause");
  });

  it("toggles the group operator to OR", () => {
    const onChange = vi.fn();
    const group: BuilderGroup = { kind: "group", op: "and", children: [makeClause("RSI")] };
    render(<DslFilterBuilder group={group} onChange={onChange} fields={FIELDS} />);

    // The OR toggle button (uppercase label rendered via CSS, text is "or").
    fireEvent.click(screen.getByRole("button", { name: "or" }));

    expect(onChange).toHaveBeenCalledWith({ ...group, op: "or" });
  });

  it("adds a nested group when '+ Group' is clicked", () => {
    const onChange = vi.fn();
    const group = makeGroup("and");
    render(<DslFilterBuilder group={group} onChange={onChange} fields={FIELDS} />);

    fireEvent.click(screen.getByText("+ Group"));

    const next = onChange.mock.calls[0][0] as BuilderGroup;
    expect(next.children).toHaveLength(1);
    expect(next.children[0].kind).toBe("group");
  });

  it("removes a clause when its remove button is clicked", () => {
    const onChange = vi.fn();
    const group: BuilderGroup = {
      kind: "group",
      op: "and",
      children: [makeClause("RSI"), makeClause("KD_K")],
    };
    render(<DslFilterBuilder group={group} onChange={onChange} fields={FIELDS} />);

    fireEvent.click(screen.getAllByLabelText("Remove condition")[0]);

    const next = onChange.mock.calls[0][0] as BuilderGroup;
    expect(next.children).toHaveLength(1);
  });
});
