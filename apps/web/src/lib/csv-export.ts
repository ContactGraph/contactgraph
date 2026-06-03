function escapeCsvField(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function buildCsv(headers: readonly string[], rows: readonly string[][]): string {
  const lines: string[] = [
    headers.map(escapeCsvField).join(","),
    ...rows.map((row: readonly string[]) => row.map(escapeCsvField).join(",")),
  ];
  return lines.join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob: Blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url: string = URL.createObjectURL(blob);
  const link: HTMLAnchorElement = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function csvFilename(prefix: string): string {
  const date: string = new Date().toISOString().slice(0, 10);
  return `${prefix}-${date}.csv`;
}
