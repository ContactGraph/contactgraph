import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

import type {
  Benefit,
  FaqItem,
  FeaturePageData,
  HowItWorksStep,
  UseCase,
} from "../data";
import { getAllFeatureSlugs, getFeaturePage } from "../data";

/* ------------------------------------------------------------------ */
/*  Static params                                                      */
/* ------------------------------------------------------------------ */

export function generateStaticParams(): { slug: string }[] {
  return getAllFeatureSlugs().map((slug: string) => ({ slug }));
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
  const page: FeaturePageData | undefined = getFeaturePage(slug);
  if (!page) return {};

  return {
    title: `${page.pageTitle} — ContactGraph`,
    description: page.pageDescription,
    alternates: { canonical: `/features/${page.slug}` },
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

export default async function FeaturePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page: FeaturePageData | undefined = getFeaturePage(slug);
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
            href="#how-it-works"
            className="text-sm text-muted-foreground no-underline hover:underline"
          >
            How it works &darr;
          </a>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how-it-works" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>How it works</SectionLabel>
          <SectionHeading>{page.howItWorksHeading}</SectionHeading>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
            {page.howItWorksSteps.map((step: HowItWorksStep) => (
              <div key={step.number} className="bg-background p-6">
                <p className="font-mono text-[11px] text-muted-foreground">
                  {step.number}
                </p>
                <h3 className="mt-3 font-bold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* BENEFITS */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Benefits</SectionLabel>
          <SectionHeading>{page.benefitsHeading}</SectionHeading>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-3">
            {page.benefits.map((benefit: Benefit) => (
              <div key={benefit.title} className="bg-background p-6">
                <h3 className="font-bold">{benefit.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {benefit.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* USE CASES */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Use cases</SectionLabel>
          <SectionHeading>{page.useCasesHeading}</SectionHeading>
          <ul className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            {page.useCases.map((useCase: UseCase) => (
              <li key={useCase.title} className="flex gap-3">
                <span
                  className="mt-1.5 block size-1.5 shrink-0 rounded-full bg-foreground"
                  aria-hidden="true"
                />
                <span>
                  <strong className="font-semibold text-foreground">
                    {useCase.title}.
                  </strong>{" "}
                  {useCase.body}
                </span>
              </li>
            ))}
          </ul>
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
            {page.ctaHeading}
          </h2>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            {page.ctaBody}
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
