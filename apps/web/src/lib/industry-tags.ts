const ORG_INDUSTRY_LABELS: Readonly<Record<string, string>> = {
  "naics:11": "Agriculture",
  "naics:21": "Mining & Energy",
  "naics:22": "Utilities",
  "naics:23": "Construction",
  "naics:31": "Manufacturing",
  "naics:42": "Wholesale",
  "naics:44": "Retail",
  "naics:48": "Transportation",
  "naics:51": "Technology & Media",
  "naics:52": "Financial Services",
  "naics:53": "Real Estate",
  "naics:54": "Professional Services",
  "naics:55": "Holding Companies",
  "naics:56": "Business Services",
  "naics:61": "Education",
  "naics:62": "Healthcare",
  "naics:71": "Arts & Entertainment",
  "naics:72": "Hospitality",
  "naics:81": "Other Services",
  "naics:92": "Government",
  nonprofit: "Nonprofit",
  venture_capital: "Venture Capital",
  legal: "Legal",
};

export function formatIndustryTag(tag: string): string {
  const normalized: string = tag.trim().toLowerCase();
  return ORG_INDUSTRY_LABELS[normalized] ?? tag;
}

export function formatIndustryTags(tags: ReadonlyArray<string>): string {
  if (tags.length === 0) {
    return "—";
  }
  return tags.map((tag: string) => formatIndustryTag(tag)).join(", ");
}
