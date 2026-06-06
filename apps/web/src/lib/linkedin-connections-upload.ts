import JSZip from "jszip";

const CONNECTIONS_CSV_PATTERN: RegExp = /(^|\/)Connections\.csv$/i;

function findConnectionsCsvEntry(zip: JSZip): JSZip.JSZipObject | null {
  const matchingNames: string[] = Object.keys(zip.files).filter((name: string) => {
    const entry: JSZip.JSZipObject | null = zip.files[name] ?? null;
    return entry !== null && !entry.dir && CONNECTIONS_CSV_PATTERN.test(name);
  });
  if (matchingNames.length === 0) {
    return null;
  }
  return zip.file(matchingNames[0]!) ?? null;
}

export async function resolveLinkedInConnectionsUpload(file: File): Promise<File> {
  const lowerName: string = file.name.toLowerCase();
  if (!lowerName.endsWith(".zip")) {
    return file;
  }

  const zip: JSZip = await JSZip.loadAsync(await file.arrayBuffer());
  const entry: JSZip.JSZipObject | null = findConnectionsCsvEntry(zip);
  if (entry === null) {
    throw new Error("Connections.csv not found in the zip file");
  }

  const content: string = await entry.async("string");
  return new File([content], "Connections.csv", { type: "text/csv" });
}
