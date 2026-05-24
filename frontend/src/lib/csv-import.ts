export function parseCSV(text: string): string[] {
  const lines = text.trim().split("\n");
  const symbols: string[] = [];
  for (const line of lines.slice(1)) { // skip header
    const cols = line.split(",");
    if (cols[0]) symbols.push(cols[0].trim().replace(/"/g, ""));
  }
  return symbols;
}
