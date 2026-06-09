export function isRecordFormDirty<T extends { [K in keyof T]: string }>(
  form: T,
  baseline: T,
): boolean {
  return (Object.keys(baseline) as Array<keyof T>).some(
    (key: keyof T) => form[key] !== baseline[key],
  );
}
