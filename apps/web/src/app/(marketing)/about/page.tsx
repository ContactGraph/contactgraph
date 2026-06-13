import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";

const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

const PAGE_TITLE = "About ContactGraph";
const PAGE_DESCRIPTION =
  "ContactGraph is a nonprofit, open-source personal relationship graph. Your contacts, your data, your agents — not a platform's.";

export const metadata: Metadata = {
  title: `${PAGE_TITLE} — ContactGraph`,
  description: PAGE_DESCRIPTION,
  alternates: { canonical: "/about" },
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

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

interface Differentiator {
  readonly label: string;
  readonly body: string;
}

const DIFFERENTIATORS: readonly Differentiator[] = [
  {
    label: "Your graph, not theirs",
    body: "LinkedIn and Facebook built their businesses on your relationships. ContactGraph builds your graph from your own data sources — contacts, calendars, inboxes — and keeps it under your control.",
  },
  {
    label: "Agent-native",
    body: "Your AI agent installs ContactGraph via MCP, connects your data, and answers your question — \"Who do I know at Stripe?\" \"Which VCs have I met?\" No app to open, no feed to scroll.",
  },
  {
    label: "More than job search",
    body: "Finding warm paths to jobs is one use case. Hiring, fundraising, sales intros, reconnecting with old friends — anything that starts with \"who do I know\" runs on the same graph.",
  },
  {
    label: "Second-degree reach",
    body: "Share graphs with trusted friends and search each other's networks — names and roles only, never emails or phone numbers. A whole community can pool their connections.",
  },
];

interface Promise {
  readonly title: string;
  readonly body: string;
}

const PROMISES: readonly Promise[] = [
  {
    title: "Never share your data",
    body: "We will never sell, license, or share your contact graph with anyone — not even anonymously. No exceptions, no asterisks.",
  },
  {
    title: "Never show ads",
    body: "Your attention is not our product. No ads, no sponsored results, no recruiter upsells. Ever.",
  },
  {
    title: "Never train on your data",
    body: "We will never use your data to train general-purpose AI models without your explicit opt-in.",
  },
  {
    title: "Open source, always",
    body: "The entire codebase is public. Read exactly what happens to your data, audit every line, or self-host the whole thing.",
  },
  {
    title: "Free forever for consumers",
    body: "No trial, no credit card, no paywall on the core product. Export or delete everything, anytime, in one click.",
  },
  {
    title: "Nonprofit structure",
    body: "ContactGraph is incorporating as a US nonprofit so we can operate in the public good, accept tax-deductible donations, and share our performance openly.",
  },
];

/* ------------------------------------------------------------------ */
/*  Page                                                               */
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

export default function AboutPage() {
  return (
    <main className="flex-1">
      {/* MISSION */}
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>Mission</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          Take back your relationships from the platforms that monetize them.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          ContactGraph is a private, open-source relationship graph built from
          your own data — contacts, calendars, inboxes — so you and your AI
          agents can actually use your network, without asking a platform for
          permission.
        </p>
      </section>

      {/* STORY */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Story</SectionLabel>
          <SectionHeading>
            Five years of trying to give people their social data back
          </SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            <p>
              For twenty years, LinkedIn, Facebook, and Instagram asked us to
              manually maintain profiles about who we know — then sold access to
              that graph. The bargain made sense in 2005. It doesn&rsquo;t
              anymore.
            </p>
            <p>
              Our founder spent five years at Joinable trying to solve the same
              problem: giving people control of their own social data.
              ContactGraph is the latest — and most radical — step in that
              journey.
            </p>
            <p>
              The insight: your messaging and calendar apps{" "}
              <em>already know</em> who you talk to, where people work, and how
              strong each tie really is. An AI agent can read that signal and
              build a richer graph than you ever would by hand — but only
              if <strong>you</strong> own the result.
            </p>
            <p>
              That&rsquo;s what ContactGraph is. A place for your personal
              social graph that belongs to you, works for you, and is accessible
              to your agents whenever they need it.
            </p>
          </div>
        </div>
      </section>

      {/* PRODUCT */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Product</SectionLabel>
          <SectionHeading>
            A personal graph, not a destination network
          </SectionHeading>
          <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground">
            We&rsquo;re not building a better LinkedIn. We&rsquo;re making the
            destination network structurally unnecessary for the things people
            actually need: finding people, getting introductions, hiring,
            fundraising, building community.
          </p>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
            {DIFFERENTIATORS.map((d: Differentiator) => (
              <div key={d.label} className="bg-background p-6">
                <h3 className="font-bold">{d.label}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {d.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TEAM */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Team</SectionLabel>
          <SectionHeading>
            More like Signal and Wikipedia than LinkedIn
          </SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            <p>
              ContactGraph is incorporating as a <strong>US nonprofit
              corporation</strong> so we can operate in the public good, accept
              tax-deductible donations, and share our performance openly —
              not answer to ad revenue or recruiter upsells.
            </p>
            <p>
              LinkedIn and Meta let us all down by using our personal social
              data for extractive profit and erecting barriers so we
              can&rsquo;t use our own data for our own benefit. We chose the
              nonprofit path because the incentives have to be right from
              day one.
            </p>
            <p>
              We&rsquo;re a small, independent team of engineers who believe
              your network belongs to you. Open source, accountable to users,
              funded by the people we serve.
            </p>
          </div>
        </div>
      </section>

      {/* TRUST */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Trust</SectionLabel>
          <SectionHeading>Our promises</SectionHeading>
          <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground">
            Your contacts are some of the most personal data you have.
            Trust is the product — so here are the commitments we make and
            never break.
          </p>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {PROMISES.map((item: Promise) => (
              <div key={item.title} className="bg-background p-6">
                <h3 className="font-bold">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {item.body}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-6 text-sm text-muted-foreground">
            Don&rsquo;t take our word for it — read the{" "}
            <a
              href={GITHUB_REPO_URL}
              className="text-foreground underline hover:no-underline"
            >
              source code
            </a>{" "}
            or the{" "}
            <Link
              href="/manifesto"
              className="text-foreground underline hover:no-underline"
            >
              manifesto
            </Link>
            .
          </p>
        </div>
      </section>

      {/* CONTACT / CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Contact</SectionLabel>
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Your network is yours. Start using it.
          </h2>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
            <a
              href={`mailto:hello@contactgraph.ai`}
              className="text-sm text-muted-foreground no-underline hover:underline"
            >
              hello@contactgraph.ai
            </a>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Nonprofit · Open source · Never shares your data · Free forever
          </p>
        </div>
      </section>
    </main>
  );
}
