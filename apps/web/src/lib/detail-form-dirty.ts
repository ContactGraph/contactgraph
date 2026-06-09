export function isRecordFormDirty<T extends Record<string, string>>(
  form: T,
  baseline: T,
): boolean {
  return (Object.keys(baseline) as Array<keyof T>).some(
    (key: keyof T) => form[key] !== baseline[key],
  );
}
