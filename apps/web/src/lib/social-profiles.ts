export interface SocialProfileEntry {
  id: string;
  platform: string;
  url: string;
}

export function normalizeSocialPlatform(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/-/g, "_")
    .replace(/[^a-z0-9_]/g, "");
}

export function socialProfilesFromRecord(
  profiles: Record<string, string>,
): SocialProfileEntry[] {
  return Object.entries(profiles)
    .filter(([platform]) => platform !== "linkedin")
    .map(([platform, url]) => ({
      id: platform,
      platform,
      url,
    }));
}

export function socialProfilesToRecord(
  entries: readonly SocialProfileEntry[],
): Record<string, string> {
  const profiles: Record<string, string> = {};
  for (const entry of entries) {
    const platform: string = normalizeSocialPlatform(entry.platform);
    const url: string = entry.url.trim();
    if (!platform || platform === "linkedin" || !url) {
      continue;
    }
    profiles[platform] = url;
  }
  return profiles;
}

export function socialProfilesSignature(
  entries: readonly SocialProfileEntry[],
): string {
  return Object.entries(socialProfilesToRecord(entries))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([platform, url]) => `${platform}|${url}`)
    .join("\n");
}

export function createEmptySocialProfileEntry(): SocialProfileEntry {
  return {
    id: crypto.randomUUID(),
    platform: "",
    url: "",
  };
}
