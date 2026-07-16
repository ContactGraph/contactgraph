import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import type { PublicCompanyDetail, PublicCompanyJob } from "../data";
import {
  companyPageDescription,
  companyPageTitle,
  fetchCompanyBySlug,
} from "../data";

export const revalidate = 3600;

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-4 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
      {children}
    </p>
  );
}

function formatJobCount(count: number): string {
  return count === 1 ? "1 open role" : `${count} open roles`;
}

function formatRemoteStatus(status: string | null): string | null {
  if (status === null) {
    return null;
  }
  if (status === "remote") {
    return "Remote";
  }
  if (status === "hybrid") {
    return "Hybrid";
  }
  return status;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const company: PublicCompanyDetail | null = await fetchCompanyBySlug(slug);
  if (company === null) {
    return {};
  }

  const title: string = companyPageTitle(company.name);
  const description: string = companyPageDescription(
    company.name,
    company.active_job_count,
  );

  return {
    title,
    description,
    alternates: { canonical: `/companies/${company.slug}` },
    openGraph: {
      title,
      description,
      type: "website",
      siteName: "ContactGraph",
      locale: "en_US",
    },
    twitter: {
      card: "summary",
      title,
      description,
    },
  };
}

export default async function PublicCompanyPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const company: PublicCompanyDetail | null = await fetchCompanyBySlug(slug);
  if (company === null) {
    notFound();
  }

  return (
    <main className="flex-1">
      {/* HERO + PITCH */}
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>Warm-path job search</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          {company.name} is hiring — do you know someone there?
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          {company.active_job_count > 0
            ? `${company.name} has ${formatJobCount(company.active_job_count)} right now. ContactGraph shows you who you already know at ${company.name} so you can reach out for a warm intro instead of applying cold.`
            : `ContactGraph shows you who you already know at ${company.name} so you can reach out for a warm intro instead of applying cold.`}
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-4">
          <Button asChild>
            <Link href="/login">Get your graph — free</Link>
          </Button>
          {company.active_job_count > 0 && (
            <a
              href="#open-roles"
              className="text-sm text-muted-foreground no-underline hover:underline"
            >
              See open roles &darr;
            </a>
          )}
        </div>
        {company.description !== null && (
          <p className="mt-8 max-w-xl text-sm leading-relaxed text-muted-foreground">
            {company.description}
          </p>
        )}
      </section>

      {/* OPEN ROLES */}
      <section id="open-roles" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Open roles</SectionLabel>
          <h2 className="mb-8 max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            {company.active_job_count > 0
              ? `${formatJobCount(company.active_job_count)} at ${company.name}`
              : `Current openings at ${company.name}`}
          </h2>
          {company.jobs.length === 0 ? (
            <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
              No active roles are listed right now.{" "}
              <Link href="/login" className="font-medium">
                Get your graph
              </Link>{" "}
              to monitor {company.name} and get alerted when new roles appear.
            </p>
          ) : (
            <ul className="divide-y divide-border border border-border">
              {company.jobs.map((job: PublicCompanyJob) => {
                const remoteLabel: string | null = formatRemoteStatus(
                  job.remote_status,
                );
                return (
                  <li key={job.job_id} className="px-4 py-4 sm:px-6">
                    <a
                      href={job.url}
                      className="text-base font-semibold no-underline hover:underline"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {job.title}
                    </a>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
                      {job.location !== null && <span>{job.location}</span>}
                      {remoteLabel !== null && <span>{remoteLabel}</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-4 text-xs text-muted-foreground">
            Role links go to the original employer posting — ContactGraph does
            not re-host job descriptions.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Get started</SectionLabel>
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Find who you know at {company.name}.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            Upload your phone contacts and LinkedIn connections once.
            ContactGraph enriches your network and shows open roles where
            someone will actually take your call.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
            <Link
              href="/company-lists/top-tech-companies-hiring"
              className="text-sm text-muted-foreground no-underline hover:underline"
            >
              Browse more employers
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Nonprofit &middot; Open source &middot; Never shares your data
            &middot; Free forever
          </p>
        </div>
      </section>
    </main>
  );
}
