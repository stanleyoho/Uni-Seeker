import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadCSV } from "@/lib/csv-export";

// The BOM that downloadCSV prepends so Excel treats the file as UTF-8.
// Built with String.fromCharCode so this source file itself stays free of
// stray U+FEFF characters (which some loaders / linters silently strip).
const BOM = String.fromCharCode(0xfeff);

// Decode the Blob's raw bytes as UTF-8 *without* stripping the leading BOM.
// Blob.text() follows the WHATWG spec and silently drops a leading U+FEFF
// when decoding — which would mask the very BOM we want to assert is there.
async function blobToText(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  return new TextDecoder("utf-8", { ignoreBOM: true }).decode(buf);
}

// Capture the Blob handed to URL.createObjectURL so we can read its text
// back asynchronously in assertions. downloadCSV constructs a Blob in jsdom
// where .text() works, so we await it.
function captureBlob(): { current: Blob | null } {
  const ref: { current: Blob | null } = { current: null };
  vi.spyOn(URL, "createObjectURL").mockImplementation((obj: Blob | MediaSource) => {
    if (obj instanceof Blob) ref.current = obj;
    return "blob:mock";
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  return ref;
}

describe("downloadCSV", () => {
  let clickSpy: ReturnType<typeof vi.fn>;
  let origCreate: typeof document.createElement;

  beforeEach(() => {
    clickSpy = vi.fn();
    // Patch document.createElement('a') so .click() doesn't actually navigate.
    origCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = origCreate(tag);
      if (tag === "a") {
        Object.defineProperty(el, "click", { value: clickSpy, writable: true });
      }
      return el;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does nothing for an empty array (no anchor, no Blob)", () => {
    const ref = captureBlob();
    downloadCSV([], "empty.csv");
    expect(ref.current).toBeNull();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("writes a UTF-8 BOM + header + rows for simple data", async () => {
    const ref = captureBlob();
    downloadCSV(
      [
        { symbol: "2330", name: "TSMC" },
        { symbol: "2317", name: "Hon Hai" },
      ],
      "stocks.csv",
    );

    expect(ref.current).not.toBeNull();
    const text = await blobToText(ref.current!);
    expect(text).toBe(`${BOM}symbol,name\n2330,TSMC\n2317,Hon Hai`);
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it("escapes values containing commas, quotes, and newlines per RFC 4180", async () => {
    const ref = captureBlob();
    downloadCSV(
      [
        { name: "has, comma" },
        { name: 'has "quote"' },
        { name: "has\nnewline" },
      ],
      "edge.csv",
    );

    const text = await blobToText(ref.current!);
    // Each tricky value should be wrapped in double quotes; embedded quotes
    // doubled. The header row stays unquoted.
    expect(text).toBe(
      `${BOM}name\n"has, comma"\n"has ""quote"""\n"has\nnewline"`,
    );
  });

  it("renders null and undefined as empty strings, not the literals", async () => {
    const ref = captureBlob();
    downloadCSV(
      [{ a: null as unknown as string, b: undefined as unknown as string, c: 0 }],
      "nulls.csv",
    );
    const text = await blobToText(ref.current!);
    // a, b → empty; c → "0" (note: numeric 0 is NOT treated as empty)
    expect(text).toBe(`${BOM}a,b,c\n,,0`);
  });

  it("uses keys from the first row as the header set", async () => {
    const ref = captureBlob();
    downloadCSV(
      [
        { a: 1, b: 2 },
        // Extra key on the second row is intentionally dropped — header is
        // derived from row 0 only. This is the documented contract.
        { a: 3, b: 4, c: 99 } as unknown as Record<string, unknown>,
      ],
      "shape.csv",
    );
    const text = await blobToText(ref.current!);
    expect(text).toBe(`${BOM}a,b\n1,2\n3,4`);
  });
});
