import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import type {
  CategoryCompaniesResult,
  CategoryCompany,
  CategoryJob,
  CategoryPageData,
} from "../data";
import {
  companyPageHref,
  fetchCategoryCompanies,
  getAllCategorySlugs,
  getCategoryPage,
  sampleCompanies,
} from "../data";

/* ------------------------------------------------------------------ */
/*  Static params                                                      */
/* ------------------------------------------------------------------ */

export function generateStaticParams(): { slug: string }[] {
  return getAllCategorySlugs().map((slug: string) => ({ slug }));
}

/* ------------------------------------------------------------------ */
/*  Metadata                                                           */
/* ------------------------------------------------------------------ */

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page: CategoryPageData | undefined = getCategoryPage(slug);
  if (!page) return {};

  return {
    title: `${page.pageTitle} — ContactGraph`,
    description: page.pageDescription,
    alternates: { canonical: `/company-lists/${page.slug}` },
    openGraph: {
      title: page.pageTitle,
      description: page.pageDescription,
      type: "website",
      siteName: "ContactGraph",
      locale: "en_US",
    },
    twitter: {
      card: "summary",
      title: page.pageTitle,
      description: page.pageDescription,
    },
  };
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-4 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
      {children}
    </p>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-8 max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
      {children}
    </h2>
  );
}

function formatJobCount(count: number): string {
  return count === 1 ? "1 open role" : `${count} open roles`;
}

function FaqJsonLd({
  faqs,
}: {
  faqs: readonly { readonly question: string; readonly answer: string }[];
}) {
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map(
      (faq: { readonly question: string; readonly answer: string }) => ({
        "@type": "Question",
        name: faq.question,
        acceptedAnswer: {
          "@type": "Answer",
          text: faq.answer,
        },
      }),
    ),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

function CompanyJobLinks({
  jobs,
}: {
  jobs: readonly CategoryJob[];
}) {
  if (jobs.length === 0) {
    return (
      <p className="mt-3 text-sm text-muted-foreground">
        Open roles available — sign in to see matched listings.
      </p>
    );
  }

  return (
    <ul className="mt-3 space-y-2">
      {jobs.map((job: CategoryJob) => (
        <li key={job.job_id}>
          <a
            href={job.url}
            className="text-sm font-medium no-underline hover:underline"
            rel="noopener noreferrer"
            target="_blank"
          >
            {job.title}
          </a>
          {job.location !== null && (
            <span className="ml-2 text-sm text-muted-foreground">
              {job.location}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default async function CompanyCategoryPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page: CategoryPageData | undefined = getCategoryPage(slug);
  if (!page) notFound();

  const liveData: CategoryCompaniesResult = await fetchCategoryCompanies(slug);
  const highlighted: readonly CategoryCompany[] = sampleCompanies(
    liveData.companies,
    4,
  );

  return (
    <main className="flex-1">
      <FaqJsonLd faqs={page.faqs} />

      {/* HERO */}
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>{page.targetKeyword}</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          {page.heroHeading}
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          {page.heroSubtitle}
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-4">
          <Button asChild>
            <Link href="/login">Get your graph — free</Link>
          </Button>
          <a
            href="#companies"
            className="text-sm text-muted-foreground no-underline hover:underline"
          >
            See who&apos;s hiring &darr;
          </a>
        </div>
      </section>

      {/* COMPANY LIST */}
      <section id="companies" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Companies hiring now</SectionLabel>
          <SectionHeading>
            {liveData.total_companies > 0
              ? `${liveData.total_companies} employers · ${liveData.total_jobs} open roles`
              : "Employers with active openings"}
          </SectionHeading>
          {liveData.companies.length === 0 ? (
            <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
              We are refreshing live hiring data for this category. Check back
              soon, or{" "}
              <Link href="/login" className="font-medium">
                get your graph
              </Link>{" "}
              to search companies where you already know someone.
            </p>
          ) : (
            <div className="space-y-6">
              {liveData.companies.map((company: CategoryCompany) => (
                <article
                  key={company.org_id}
                  className="border border-border p-6"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <h3 className="text-lg font-bold">
                      <Link
                        href={companyPageHref(company.slug)}
                        className="no-underline hover:underline"
                      >
                        {company.name}
                      </Link>
                    </h3>
                    <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                      {formatJobCount(company.active_job_count)}
                    </span>
                  </div>
                  {company.description !== null && (
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {company.description}
                    </p>
                  )}
                  <CompanyJobLinks jobs={company.sample_jobs} />
                </article>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* WHY THIS CATEGORY MATTERS */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Why this matters</SectionLabel>
          <SectionHeading>Why this category matters</SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            {page.whyThisCategoryMatters.map((paragraph: string) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        </div>
      </section>

      {/* SAMPLE COMPANIES */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Highlighted employers</SectionLabel>
          <SectionHeading>Sample companies hiring in this space</SectionHeading>
          {highlighted.length === 0 ? (
            <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
              Live employer highlights will appear here as our job database
              updates.
            </p>
          ) : (
            <div className="grid gap-6 sm:grid-cols-2">
              {highlighted.map(
                (company: CategoryCompany, index: number) => (
                  <div
                    key={company.org_id}
                    className="border border-border p-6"
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <h3 className="text-lg font-bold">
                        <Link
                          href={companyPageHref(company.slug)}
                          className="no-underline hover:underline"
                        >
                          {company.name}
                        </Link>
                      </h3>
                    </div>
                    {company.description !== null && (
                      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        {company.description}
                      </p>
                    )}
                    <p className="mt-3 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                      {formatJobCount(company.active_job_count)}
                    </p>
                    <CompanyJobLinks jobs={company.sample_jobs} />
                  </div>
                ),
              )}
            </div>
          )}
        </div>
      </section>

      {/* NETWORK FIT */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Network fit</SectionLabel>
          <SectionHeading>{page.networkFitHeading}</SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            {page.networkFitBody.map((paragraph: string) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>FAQ</SectionLabel>
          <SectionHeading>Frequently asked questions</SectionHeading>
          <dl className="max-w-xl space-y-8">
            {page.faqs.map(
              (faq: { readonly question: string; readonly answer: string }) => (
                <div key={faq.question}>
                  <dt className="font-bold">{faq.question}</dt>
                  <dd className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {faq.answer}
                  </dd>
                </div>
              ),
            )}
          </dl>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Get started</SectionLabel>
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Find a warm path into companies that are hiring.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            Upload your contacts once. ContactGraph shows you open roles at
            employers where someone you know can actually help.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
            <a
              href="mailto:hello@contactgraph.ai"
              className="text-sm text-muted-foreground no-underline hover:underline"
            >
              hello@contactgraph.ai
            </a>
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
