import type { Metadata } from "next";
import Link from "next/link";

import {
  getAllAlternativesPages,
  type AlternativesPageData,
} from "@/app/(marketing)/alternatives/data";
import {
  getAllCategoryPages,
  type CategoryPageData,
} from "@/app/(marketing)/company-lists/data";
import {
  getAllGuidePages,
  guidePageHref,
  type GuidePageData,
} from "@/app/(marketing)/guides/data";
import { companyListPageHref } from "@/lib/company-slug";
import { Button } from "@/components/ui/button";

const PAGE_TITLE = "Resources for job seekers";
const PAGE_DESCRIPTION =
  "Live hiring lists, job-search tool comparisons, and warm intro paths through your network.";

export const metadata: Metadata = {
  title: `${PAGE_TITLE} — ContactGraph`,
  description: PAGE_DESCRIPTION,
  alternates: { canonical: "/resources" },
  openGraph: {
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    type: "website",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
  },
};

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

export default function ResourcesPage() {
  const categoryPages: readonly CategoryPageData[] = getAllCategoryPages();
  const alternativesPages: readonly AlternativesPageData[] =
    getAllAlternativesPages();
  const guidePages: readonly GuidePageData[] = getAllGuidePages();

  return (
    <main className="flex-1">
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>Resources</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          Who&apos;s hiring — and who you know there.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          Browse live employer lists with current open-role counts, compare
          job-search tools to ContactGraph, and find a warm intro path before
          you apply.
        </p>
        <div className="mt-7">
          <Button asChild>
            <Link href="/login">Get your graph — free</Link>
          </Button>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Company lists</SectionLabel>
          <SectionHeading>Employers hiring right now</SectionHeading>
          <p className="mb-10 max-w-xl text-base leading-relaxed text-muted-foreground">
            Updated from ContactGraph&apos;s live job database. Pick a category
            to see employers, open roles, and links to each company&apos;s
            current openings.
          </p>
          <ul className="divide-y divide-border border border-border">
            {categoryPages.map((page: CategoryPageData) => (
              <li key={page.slug}>
                <Link
                  href={companyListPageHref(page.slug)}
                  className="block px-4 py-5 no-underline transition-colors hover:bg-secondary sm:px-6"
                >
                  <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                    {page.targetKeyword}
                  </p>
                  <h3 className="mt-1 text-lg font-bold text-foreground">
                    {page.pageTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                    {page.pageDescription}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Alternatives</SectionLabel>
          <SectionHeading>Job search tool comparisons</SectionHeading>
          <p className="mb-10 max-w-xl text-base leading-relaxed text-muted-foreground">
            Honest comparisons of popular job-search and networking tools — and
            how ContactGraph&apos;s warm-path approach differs.
          </p>
          <ul className="divide-y divide-border border border-border">
            {alternativesPages.map((page: AlternativesPageData) => (
              <li key={page.slug}>
                <Link
                  href={`/alternatives/${page.slug}`}
                  className="block px-4 py-5 no-underline transition-colors hover:bg-secondary sm:px-6"
                >
                  <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                    {page.targetKeyword}
                  </p>
                  <h3 className="mt-1 text-lg font-bold text-foreground">
                    {page.pageTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                    {page.pageDescription}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section id="guides" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Guides</SectionLabel>
          <SectionHeading>Connect AI to your LinkedIn network</SectionHeading>
          <p className="mb-10 max-w-xl text-base leading-relaxed text-muted-foreground">
            LinkedIn doesn&apos;t offer consumer API access for AI tools. These
            guides explain the problem, compare approaches, and show how to
            connect Claude to your contacts safely.
          </p>
          <ul className="divide-y divide-border border border-border">
            {guidePages.map((page: GuidePageData) => (
              <li key={page.slug}>
                <Link
                  href={guidePageHref(page.slug)}
                  className="block px-4 py-5 no-underline transition-colors hover:bg-secondary sm:px-6"
                >
                  <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                    {page.targetKeyword}
                  </p>
                  <h3 className="mt-1 text-lg font-bold text-foreground">
                    {page.pageTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                    {page.pageDescription}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Get started</SectionLabel>
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Lists show who&apos;s hiring. ContactGraph shows who you know.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            Upload your contacts once. We match open roles at these employers to
            people in your network — so every application can start with a warm
            intro.
          </p>
          <div className="mt-7">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
