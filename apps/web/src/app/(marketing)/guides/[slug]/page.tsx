import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import type {
  ExternalReference,
  FaqItem,
  GuideApproach,
  GuidePageData,
  GuideSolutionStep,
} from "../data";
import { getAllGuideSlugs, getGuidePage } from "../data";

/* ------------------------------------------------------------------ */
/*  Static params                                                      */
/* ------------------------------------------------------------------ */

export function generateStaticParams(): { slug: string }[] {
  return getAllGuideSlugs().map((slug: string) => ({ slug }));
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
  const page: GuidePageData | undefined = getGuidePage(slug);
  if (!page) return {};

  return {
    title: `${page.pageTitle} — ContactGraph`,
    description: page.pageDescription,
    alternates: { canonical: `/guides/${page.slug}` },
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

function FaqJsonLd({ faqs }: { faqs: readonly FaqItem[] }) {
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq: FaqItem) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
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

export default async function GuidePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page: GuidePageData | undefined = getGuidePage(slug);
  if (!page) notFound();

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
            href="#approaches"
            className="text-sm text-muted-foreground no-underline hover:underline"
          >
            Compare approaches &darr;
          </a>
        </div>
        <p className="mt-6 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          Last updated {page.lastUpdated}
        </p>
      </section>

      {/* THE PROBLEM */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>The problem</SectionLabel>
          <SectionHeading>{page.problemHeading}</SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            {page.problemParagraphs.map((paragraph: string) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
          {page.references.length > 0 && (
            <div className="mt-8 max-w-xl">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                Further reading
              </p>
              <ul className="space-y-2 text-sm">
                {page.references.map((ref: ExternalReference) => (
                  <li key={ref.url}>
                    <a
                      href={ref.url}
                      className="font-medium no-underline hover:underline"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {ref.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {/* AVAILABLE APPROACHES */}
      <section id="approaches" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Available approaches</SectionLabel>
          <SectionHeading>How people try to connect AI to LinkedIn</SectionHeading>
          <div className="space-y-6">
            {page.approaches.map(
              (approach: GuideApproach, index: number) => (
                <div
                  key={approach.name}
                  className="border border-border p-6"
                >
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <h3 className="text-lg font-bold">{approach.name}</h3>
                  </div>
                  <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                    {approach.summary}
                  </p>
                  <div className="mt-4 grid gap-px border border-border bg-border sm:grid-cols-2">
                    <div className="bg-background p-4">
                      <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                        Pros
                      </p>
                      <ul className="space-y-1.5 text-sm text-muted-foreground">
                        {approach.pros.map((pro: string) => (
                          <li key={pro} className="flex gap-2">
                            <span className="shrink-0 text-foreground">+</span>
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
                        {approach.cons.map((con: string) => (
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

      {/* HOW CONTACTGRAPH SOLVES IT */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>The solution</SectionLabel>
          <SectionHeading>{page.solutionHeading}</SectionHeading>
          <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground">
            {page.solutionIntro}
          </p>
          <ol className="max-w-xl space-y-6">
            {page.solutionSteps.map(
              (step: GuideSolutionStep, index: number) => (
                <li key={step.title} className="flex gap-4">
                  <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center border border-border font-mono text-[11px]">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="font-bold">{step.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {step.description}
                    </p>
                  </div>
                </li>
              ),
            )}
          </ol>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>FAQ</SectionLabel>
          <SectionHeading>Frequently asked questions</SectionHeading>
          <dl className="max-w-xl space-y-8">
            {page.faqs.map((faq: FaqItem) => (
              <div key={faq.question}>
                <dt className="font-bold">{faq.question}</dt>
                <dd className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {faq.answer}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Get started</SectionLabel>
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Export once. Connect any AI. Own your network.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            Upload your LinkedIn connections and phone contacts. ContactGraph
            builds your graph and exposes it to Claude, ChatGPT, and any MCP
            client — free, open source, and never sells your data.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
            <a
              href="https://api.contactgraph.ai/skill.md"
              className="text-sm text-muted-foreground no-underline hover:underline"
              rel="noopener noreferrer"
              target="_blank"
            >
              MCP setup guide
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
