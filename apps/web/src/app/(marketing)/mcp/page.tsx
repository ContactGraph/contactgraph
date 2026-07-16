import type { Metadata } from "next";
import Link from "next/link";

import { CopyField } from "./copy-field";
import { Button } from "@/components/ui/button";

const API_BASE = "https://api.contactgraph.ai";
const MCP_URL = `${API_BASE}/mcp`;
const SKILL_URL = `${API_BASE}/skill.md`;
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";
const README_URL = `${GITHUB_REPO_URL}#readme`;

const PAGE_TITLE = "Connect ContactGraph to your AI (MCP server)";
const PAGE_DESCRIPTION =
  "Connect Claude, ChatGPT, Gemini, or any MCP client to your ContactGraph network. Remote MCP server over Streamable HTTP with OAuth 2.1 — no API keys, just sign in with Google.";

export const metadata: Metadata = {
  title: `${PAGE_TITLE} — ContactGraph`,
  description: PAGE_DESCRIPTION,
  alternates: { canonical: "/mcp" },
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

interface ClientGuide {
  readonly name: string;
  readonly blurb: string;
  readonly steps: readonly string[];
  readonly note?: string;
}

const CLIENT_GUIDES: readonly ClientGuide[] = [
  {
    name: "Claude",
    blurb: "Claude.ai and Claude Desktop, via custom connectors.",
    steps: [
      "In Claude, open Customize (top of the left sidebar) → Connectors → + → Add custom connector.",
      "Name it ContactGraph and paste the MCP URL above as the Remote MCP server URL.",
      "Leave Client ID / Secret empty (dynamic client registration), click Connect, and sign in with Google.",
      "Start a new chat, enable the ContactGraph connector, and ask e.g. \u201cWhat VCs do I know?\u201d",
    ],
    note: "If tools stop responding after a while, disconnect and reconnect the connector to refresh the token.",
  },
  {
    name: "ChatGPT",
    blurb: "Custom apps via Developer Mode (Plus, Pro, Business, Enterprise on the web).",
    steps: [
      "In ChatGPT Settings → Apps, open Advanced settings → Developer mode and turn it on.",
      "Click Create app, name it ContactGraph, paste the MCP URL, and choose OAuth (leave Client ID / Secret empty).",
      "Check \u201cI trust this application\u201d, click Create, and complete the Google sign-in.",
      "In a new chat, open the + menu → Developer mode → select ContactGraph, then ask your question.",
    ],
    note: "Write actions (sync, connect) ask for confirmation — review each tool call before approving.",
  },
  {
    name: "Gemini CLI",
    blurb: "Google\u2019s open-source terminal agent, with automatic OAuth discovery.",
    steps: [
      "Run: gemini mcp add -s user --transport http contactgraph https://api.contactgraph.ai/mcp",
      "Start the Gemini CLI and run /mcp auth contactgraph, then sign in with Google in the browser.",
      "Verify with /mcp (tools appear as mcp_contactgraph_*), then ask your question.",
    ],
    note: "OAuth needs a local browser, so headless SSH sessions require port forwarding.",
  },
  {
    name: "OpenClaw",
    blurb: "Self-hosted agent gateway (WhatsApp, Telegram, and more).",
    steps: [
      "Install the skill: curl -s https://api.contactgraph.ai/skill.md -o ~/.openclaw/skills/contactgraph/SKILL.md",
      "Add contactgraph to your MCP config pointing at the MCP URL (the OAuth bridge plugin handles PKCE and refresh).",
      "Run /mcp auth contactgraph and sign in with Google; verify tools with /mcp tools.",
    ],
  },
];

const FLOW_STEPS: readonly string[] = [
  "connect_source \u2014 link Gmail (open the Google consent URL once)",
  "sync_source \u2014 import your contacts, then poll get_source_status until it reports partial or complete",
  "start_enrichment \u2014 resolve employers, roles, and social profiles (poll get_enrichment_status)",
  "query_network \u2014 ask questions like \u201cWho do I know at Stripe?\u201d",
];

const EXAMPLE_QUESTIONS: readonly string[] = [
  "Who do I know at Stripe?",
  "What VCs have I met?",
  "Find warm paths into AI startups that are hiring.",
  "Who did I talk to about hiring?",
];

/* ------------------------------------------------------------------ */
/*  Presentational helpers                                             */
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
    <h2 className="mb-6 max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
      {children}
    </h2>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function McpDocsPage() {
  return (
    <main className="flex-1">
      {/* HERO + ESSENTIALS */}
      <section className="mx-auto max-w-5xl px-4 pb-14 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>Model Context Protocol</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          Connect your AI to your network.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          ContactGraph is a remote MCP server. Point Claude, ChatGPT, Gemini, or
          any MCP client at it and your assistant can answer &ldquo;who do I know
          at&hellip;&rdquo; questions using your own enriched graph — no scraping,
          no API keys, just sign in with Google.
        </p>

        <div className="mt-10 grid gap-px border border-border bg-border sm:grid-cols-3">
          <div className="bg-background p-6 sm:col-span-2">
            <h2 className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              MCP server URL
            </h2>
            <div className="mt-3">
              <CopyField value={MCP_URL} ariaLabel="Copy MCP server URL" />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Streamable HTTP transport. A trailing slash is fine. This is an
              endpoint for agents — opening it in a browser will not show a page.
            </p>
          </div>
          <div className="bg-background p-6">
            <h2 className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              Authentication
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              OAuth 2.1 with dynamic client registration. No Client ID or Secret
              — your MCP client registers automatically and you sign in with
              Google.
            </p>
          </div>
        </div>

        <div className="mt-6 rounded-md border border-border bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
          <strong className="text-foreground">First:</strong> create your free
          account and upload your contacts / LinkedIn connections. MCP connects
          an assistant to <em>your</em> graph, so there needs to be a graph to
          query.{" "}
          <Link
            href="/login"
            className="text-foreground underline hover:no-underline"
          >
            Get your graph
          </Link>
          .
        </div>
      </section>

      {/* PER-CLIENT SETUP */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Setup</SectionLabel>
          <SectionHeading>Add ContactGraph to your client</SectionHeading>
          <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
            {CLIENT_GUIDES.map((guide: ClientGuide) => (
              <div key={guide.name} className="bg-background p-6">
                <h3 className="text-lg font-bold">{guide.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {guide.blurb}
                </p>
                <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground marker:text-muted-foreground/60">
                  {guide.steps.map((step: string) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                {guide.note ? (
                  <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                    <strong className="text-foreground">Note:</strong>{" "}
                    {guide.note}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
          <p className="mt-6 text-sm text-muted-foreground">
            Also works with Cursor, Claude Code, and any MCP-compatible client.
            For Gemini Enterprise and other advanced setups, see the{" "}
            <a
              href={README_URL}
              className="text-foreground underline hover:no-underline"
            >
              full README
            </a>
            .
          </p>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>How it works</SectionLabel>
          <SectionHeading>What your agent does once connected</SectionHeading>
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                The server exposes a small set of tools. A typical run:
              </p>
              <ol className="list-decimal space-y-3 pl-5 text-sm leading-relaxed text-muted-foreground marker:text-muted-foreground/60">
                {FLOW_STEPS.map((step: string) => (
                  <li key={step}>
                    <code className="font-mono text-foreground">
                      {step.split(" \u2014 ")[0]}
                    </code>
                    {step.includes(" \u2014 ")
                      ? ` — ${step.split(" \u2014 ")[1]}`
                      : null}
                  </li>
                ))}
              </ol>
            </div>
            <div>
              <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                Then just ask, in plain language:
              </p>
              <ul className="space-y-2">
                {EXAMPLE_QUESTIONS.map((q: string) => (
                  <li
                    key={q}
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    &ldquo;{q}&rdquo;
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* TERMINAL AGENTS / SKILL */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <SectionLabel>Terminal &amp; custom agents</SectionLabel>
          <SectionHeading>Prefer the raw API or a skill file?</SectionHeading>
          <p className="mb-6 max-w-xl text-base leading-relaxed text-muted-foreground">
            Any agent that can make HTTP requests can use the same tool surface
            over REST, or load the published skill file for step-by-step
            instructions. Both live on the API host.
          </p>
          <div className="max-w-2xl">
            <CopyField value={SKILL_URL} ariaLabel="Copy skill file URL" />
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button asChild>
              <a href={SKILL_URL}>Read the skill file</a>
            </Button>
            <a
              href={GITHUB_REPO_URL}
              className="text-sm text-muted-foreground no-underline hover:underline"
            >
              View source on GitHub
            </a>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          <h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">
            Your network is yours. Point your agent at it.
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
            Nonprofit · Open source · Never shares your data · Free forever
          </p>
        </div>
      </section>
    </main>
  );
}
