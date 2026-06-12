import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";

const API_BASE = "https://api.contactgraph.ai";
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

const PAGE_TITLE = "ContactGraph — You already know someone at your next job.";
const PAGE_DESCRIPTION =
  "Merge your phone contacts and LinkedIn connections into one searchable network, then find open roles at companies where you already know someone. Private, open source, free.";

export const metadata: Metadata = {
  title: PAGE_TITLE,
  description: PAGE_DESCRIPTION,
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

interface SampleConnection {
  readonly name: string;
  readonly role: string;
  readonly source: string;
}

const SAMPLE_CONNECTIONS: readonly SampleConnection[] = [
  {
    name: "Sarah Kim",
    role: "Product Manager",
    source: "ex-coworker · phone + LinkedIn",
  },
  {
    name: "David Mota",
    role: "Engineering Manager",
    source: "LinkedIn",
  },
  {
    name: "Priya Natarajan",
    role: "Technical Recruiter",
    source: "phone",
  },
];

interface Step {
  readonly number: string;
  readonly title: string;
  readonly body: string;
}

const STEPS: readonly Step[] = [
  {
    number: "01",
    title: "Export two files",
    body: "Phone contacts (.vcf) and LinkedIn connections (.csv). We walk you through both exports — about ten minutes, and you only do it once.",
  },
  {
    number: "02",
    title: "We enrich your network",
    body: "Public web data fills in current employer, role, and industry — including for the people you haven't talked to in years.",
  },
  {
    number: "03",
    title: "Search what you couldn't before",
    body: "By company, role, industry, or name. \u201cWho do I know at Figma?\u201d takes two seconds instead of an hour of scrolling.",
  },
  {
    number: "04",
    title: "See jobs with a warm path",
    body: "Open roles at companies where you already know someone — so every application starts with an intro instead of a void.",
  },
];

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-8 max-w-xl text-2xl font-semibold tracking-tight sm:text-3xl">
      {children}
    </h2>
  );
}

function TrustLine() {
  return (
    <p className="text-xs text-muted-foreground">
      Open source · Never contacts anyone · Export or delete anytime
    </p>
  );
}

function SampleSearchPanel() {
  return (
    <figure className="w-full">
      <div className="border border-border">
        <div className="border-b border-border px-4 py-3">
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
            Who do you know at&hellip;
          </p>
          <p className="mt-1 font-mono text-base">
            stripe<span className="animate-pulse">▍</span>
          </p>
        </div>
        <ul className="divide-y divide-border">
          {SAMPLE_CONNECTIONS.map((person: SampleConnection) => (
            <li key={person.name} className="px-4 py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{person.name}</span>
                <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                  {person.source}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">{person.role}</p>
            </li>
          ))}
        </ul>
        <div className="border-t border-border bg-secondary px-4 py-3">
          <p className="text-sm font-medium">
            4 open roles at Stripe match &ldquo;product manager&rdquo; &rarr;
          </p>
        </div>
      </div>
      <figcaption className="mt-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
        Your first search, ten minutes from now
      </figcaption>
    </figure>
  );
}

export default function HomePage() {
  const mcpPath = `${API_BASE}/mcp`;

  return (
    <main className="flex-1">
      {/* ABOVE THE FOLD — hero + proof artifact */}
      <section className="mx-auto grid max-w-5xl items-center gap-12 px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:grid-cols-2 lg:gap-16">
        <div>
          <p className="mb-4 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
            Warm-path job search
          </p>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
            You already know someone at your next job.
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-muted-foreground">
            ContactGraph merges your phone contacts and LinkedIn connections
            into one searchable network — then finds open roles at companies
            where someone will actually answer your message.
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
          <div className="mt-4">
            <TrustLine />
          </div>
        </div>
        <SampleSearchPanel />
      </section>

      {/* HOW IT WORKS */}
      <section id="how-it-works" className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading>
            Two files in. A warm-path job list out.
          </SectionHeading>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step: Step) => (
              <div key={step.number} className="bg-background p-6">
                <p className="font-mono text-[11px] text-muted-foreground">
                  {step.number}
                </p>
                <h3 className="mt-3 font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* WHY NOT LINKEDIN */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading>Couldn&rsquo;t I just search LinkedIn?</SectionHeading>
          <div className="max-w-xl space-y-4 text-base leading-relaxed text-muted-foreground">
            <p>
              You could try. But LinkedIn won&rsquo;t search your phone
              contacts, its own-connection search barely works, and job boards
              have no idea who you know.
            </p>
            <p>
              Your network is real — it&rsquo;s just split across apps that
              don&rsquo;t talk to each other. ContactGraph is the one place
              where all of it is searchable at once, with current employers
              filled in even for the people whose details went stale years ago.
            </p>
          </div>
        </div>
      </section>

      {/* TRUST */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading>
            Built to be trusted with your contact list.
          </SectionHeading>
          <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground">
            Your contacts are some of the most personal data you have.
            ContactGraph is designed so you don&rsquo;t have to take its
            safety on faith.
          </p>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-3">
            <div className="bg-background p-6">
              <h3 className="font-semibold">Private by default</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Your graph is visible only to you. ContactGraph never emails,
                messages, or notifies anyone in it — and never sells your data.
                Export or delete everything, anytime.
              </p>
            </div>
            <div className="bg-background p-6">
              <h3 className="font-semibold">Open source</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Don&rsquo;t take our word for it. The entire codebase is{" "}
                <a href={GITHUB_REPO_URL}>on GitHub</a> — read exactly what
                happens to your data, or run it yourself.
              </p>
            </div>
            <div className="bg-background p-6">
              <h3 className="font-semibold">Free for personal use</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                No trial, no card, no paywall on the core product. Built for
                people mid-job-search, not against them.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* SECOND DEGREE */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading>
            When your network isn&rsquo;t enough, borrow a friend&rsquo;s.
          </SectionHeading>
          <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
            Share graphs with trusted friends and search each other&rsquo;s
            networks for second-degree intros. Laid off together? A whole
            cohort can pool their networks and job-hunt as one.
          </p>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <h2 className="max-w-xl text-2xl font-semibold tracking-tight sm:text-3xl">
            Ten minutes from now, you&rsquo;ll know exactly who to ask.
          </h2>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button asChild>
              <Link href="/login">Get your graph — free</Link>
            </Button>
            <TrustLine />
          </div>
          <p className="mt-10 text-xs text-muted-foreground">
            ContactGraph also works as an MCP server for Claude, ChatGPT, and
            Gemini (via <a href={mcpPath}>MCP</a>) and with terminal agents
            (via <a href={`${API_BASE}/skill.md`}>skill.md</a>).
          </p>
        </div>
      </section>
    </main>
  );
}
