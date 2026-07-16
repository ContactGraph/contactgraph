import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import type { RelatedGuideLink } from "@/app/(marketing)/guides/data";
import { guidePageHref, LINKEDIN_JOBS_RELATED_GUIDES } from "@/app/(marketing)/guides/data";

import type { Alternative, AlternativesPageData } from "../data";
import { getAllAlternativesSlugs, getAlternativesPage } from "../data";

/* ------------------------------------------------------------------ */
/*  Static params                                                      */
/* ------------------------------------------------------------------ */

export function generateStaticParams(): { slug: string }[] {
  return getAllAlternativesSlugs().map((slug: string) => ({ slug }));
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
  const page: AlternativesPageData | undefined = getAlternativesPage(slug);
  if (!page) return {};

  return {
    title: `${page.pageTitle} — ContactGraph`,
    description: page.pageDescription,
    alternates: { canonical: `/alternatives/${page.slug}` },
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

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default async function AlternativesPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page: AlternativesPageData | undefined = getAlternativesPage(slug);
  if (!page) notFound();

  const relatedGuides: readonly RelatedGuideLink[] =
    slug === "linkedin-jobs-alternatives" ? LINKEDIN_JOBS_RELATED_GUIDES : [];

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
            href="#comparison"
            className="text-sm text-muted-foreground no-underline hover:underline"
          >
            See the comparison &darr;
          </a>
        </div>
      </section>

      {/* WHO THIS IS FOR */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Who this is for</SectionLabel>
          <SectionHeading>
            Searching for {page.competitor} alternatives?
          </SectionHeading>
          <ul className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            {page.whoThisIsFor.map((item: string) => (
              <li key={item} className="flex gap-3">
                <span
                  className="mt-1.5 block size-1.5 shrink-0 rounded-full bg-foreground"
                  aria-hidden="true"
                />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* TOP ALTERNATIVES */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Top alternatives</SectionLabel>
          <SectionHeading>
            The best {page.competitor} alternatives in 2025
          </SectionHeading>
          <div className="space-y-6">
            {page.alternatives.map(
              (alt: Alternative, index: number) => (
                <div
                  key={alt.name}
                  className="border border-border p-6"
                >
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <h3 className="text-lg font-bold">{alt.name}</h3>
                  </div>
                  <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                    {alt.tagline}
                  </p>
                  <div className="mt-4 grid gap-px border border-border bg-border sm:grid-cols-2">
                    <div className="bg-background p-4">
                      <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                        Pros
                      </p>
                      <ul className="space-y-1.5 text-sm text-muted-foreground">
                        {alt.pros.map((pro: string) => (
                          <li key={pro} className="flex gap-2">
                            <span className="shrink-0 text-foreground">
                              +
                            </span>
                            <span>{pro}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-background p-4">
                      <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                        Cons
                      </p>
                      <ul className="space-y-1.5 text-sm text-muted-foreground">
                        {alt.cons.map((con: string) => (
                          <li key={con} className="flex gap-2">
                            <span className="shrink-0">&ndash;</span>
                            <span>{con}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      {/* COMPARISON TABLE */}
      <section id="comparison" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Comparison</SectionLabel>
          <SectionHeading>
            {page.competitor} vs ContactGraph
          </SectionHeading>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border border-border text-sm">
              <thead>
                <tr className="bg-secondary">
                  <th className="border border-border px-4 py-3 text-left font-bold">
                    Feature
                  </th>
                  <th className="border border-border px-4 py-3 text-left font-bold">
                    {page.competitor}
                  </th>
                  <th className="border border-border px-4 py-3 text-left font-bold">
                    ContactGraph
                  </th>
                </tr>
              </thead>
              <tbody>
                {page.comparisonRows.map(
                  (row: {
                    readonly feature: string;
                    readonly competitorValue: string;
                    readonly contactGraphValue: string;
                  }) => (
                    <tr key={row.feature}>
                      <td className="border border-border px-4 py-3 font-medium">
                        {row.feature}
                      </td>
                      <td className="border border-border px-4 py-3 text-muted-foreground">
                        {row.competitorValue}
                      </td>
                      <td className="border border-border px-4 py-3">
                        {row.contactGraphValue}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* RELATED GUIDES */}
      {relatedGuides.length > 0 && (
        <section className="border-t border-border">
          <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
            <SectionLabel>Guides</SectionLabel>
            <SectionHeading>Connect AI to your LinkedIn network</SectionHeading>
            <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground">
              Looking for a Claude connector for LinkedIn or a LinkedIn MCP
              server? These guides explain why direct integration isn&apos;t
              possible — and how ContactGraph solves it safely.
            </p>
            <ul className="divide-y divide-border border border-border">
              {relatedGuides.map((guide: RelatedGuideLink) => (
                <li key={guide.slug}>
                  <Link
                    href={guidePageHref(guide.slug)}
                    className="block px-4 py-5 no-underline transition-colors hover:bg-secondary sm:px-6"
                  >
                    <h3 className="text-lg font-bold text-foreground">
                      {guide.title}
                    </h3>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {guide.description}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

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
            Your network is yours. Start using it.
          </h2>
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
