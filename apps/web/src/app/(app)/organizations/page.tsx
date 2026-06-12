import { redirect } from "next/navigation";

export default async function OrganizationsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const resolved: Record<string, string | string[] | undefined> =
    await searchParams;
  const params = new URLSearchParams();
  params.set("tab", "organizations");

  for (const [key, value] of Object.entries(resolved)) {
    if (value === undefined) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
    } else {
      params.set(key, value);
    }
  }

  redirect(`/graph?${params.toString()}`);
}
