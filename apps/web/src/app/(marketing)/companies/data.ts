import { env } from "@/lib/env";

export interface PublicCompanyJob {
  readonly job_id: string;
  readonly title: string;
  readonly location: string | null;
  readonly url: string;
  readonly remote_status: string | null;
  readonly posted_at: string | null;
}

export interface PublicCompanyDetail {
  readonly org_id: string;
  readonly slug: string;
  readonly name: string;
  readonly primary_domain: string | null;
  readonly description: string | null;
  readonly company_size_band: string | null;
  readonly active_job_count: number;
  readonly jobs: readonly PublicCompanyJob[];
  readonly generated_at: string;
}

export async function fetchCompanyBySlug(
  slug: string,
): Promise<PublicCompanyDetail | null> {
  const apiUrl: string = env.apiUrl.replace(/\/$/, "");
  const url: string = `${apiUrl}/api/public/companies/${encodeURIComponent(slug)}`;

  try {
    const response: Response = await fetch(url, {
      next: { revalidate: 3600 },
    });

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      return null;
    }

    const payload: unknown = await response.json();
    return parsePublicCompanyDetail(payload);
  } catch {
    return null;
  }
}

function parsePublicCompanyDetail(payload: unknown): PublicCompanyDetail | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  const data: Record<string, unknown> = payload as Record<string, unknown>;
  const orgId: string | null = typeof data.org_id === "string" ? data.org_id : null;
  const slug: string | null = typeof data.slug === "string" ? data.slug : null;
  const name: string | null = typeof data.name === "string" ? data.name : null;
  const activeJobCount: number | null =
    typeof data.active_job_count === "number" ? data.active_job_count : null;

  if (orgId === null || slug === null || name === null || activeJobCount === null) {
    return null;
  }

  const jobsRaw: unknown = data.jobs;
  const jobs: PublicCompanyJob[] = Array.isArray(jobsRaw)
    ? jobsRaw
        .map(parsePublicCompanyJob)
        .filter((job: PublicCompanyJob | null): job is PublicCompanyJob => job !== null)
    : [];

  return {
    org_id: orgId,
    slug,
    name,
    primary_domain:
      typeof data.primary_domain === "string" ? data.primary_domain : null,
    description: typeof data.description === "string" ? data.description : null,
    company_size_band:
      typeof data.company_size_band === "string" ? data.company_size_band : null,
    active_job_count: activeJobCount,
    jobs,
    generated_at:
      typeof data.generated_at === "string"
        ? data.generated_at
        : new Date().toISOString(),
  };
}

function parsePublicCompanyJob(raw: unknown): PublicCompanyJob | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }

  const item: Record<string, unknown> = raw as Record<string, unknown>;
  const jobId: string | null = typeof item.job_id === "string" ? item.job_id : null;
  const title: string | null = typeof item.title === "string" ? item.title : null;
  const url: string | null = typeof item.url === "string" ? item.url : null;

  if (jobId === null || title === null || url === null) {
    return null;
  }

  return {
    job_id: jobId,
    title,
    location: typeof item.location === "string" ? item.location : null,
    url,
    remote_status:
      typeof item.remote_status === "string" ? item.remote_status : null,
    posted_at: typeof item.posted_at === "string" ? item.posted_at : null,
  };
}

function formatJobCount(count: number): string {
  return count === 1 ? "1 open role" : `${count} open roles`;
}

export function companyPageTitle(name: string): string {
  return `${name} Jobs — ContactGraph`;
}

export function companyPageDescription(
  name: string,
  jobCount: number,
): string {
  return `${formatJobCount(jobCount)} at ${name}. Find a warm intro path through your network with ContactGraph.`;
}
