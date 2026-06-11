import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { MarketingMain, MarketingProse } from "./components/marketing-prose";

const API_BASE = "https://api.contactgraph.ai";
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

const PAGE_TITLE = "ContactGraph — You already know the right people.";
const PAGE_DESCRIPTION =
  "Upload your phone contacts and LinkedIn connections. ContactGraph enriches your network and finds warm paths to companies — including open roles for job search.";

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

export default function HomePage() {
  const mcpPath = `${API_BASE}/mcp`;

  return (
    <MarketingMain>
      <MarketingProse>
        <h1>You already know the right people. ContactGraph helps you find them.</h1>
        <p>
          You have hundreds of professional contacts scattered across your phone,
          LinkedIn, and email — but when you need a warm intro or a connection at a
          specific company, you can&rsquo;t search any of it.
        </p>
        <p>
          Upload your phone contacts and LinkedIn connections. ContactGraph enriches
          them with current employer, role, and industry data, then shows you exactly
          who you know at any company — and what open roles they have.
        </p>

        <h2>Supercharge your job search</h2>
        <p>
          ContactGraph finds open roles at companies where you already have warm
          connections — no cold applications. Share your graph with trusted friends
          and discover second-degree intros too.
        </p>

        <p>
          <strong>How it works</strong>
        </p>
        <ol>
          <li>Upload phone contacts (.vcf) and LinkedIn connections (.csv)</li>
          <li>We enrich your network with web data — employer, role, industry</li>
          <li>Search by company, role, industry, or name</li>
          <li>Share your graph with trusted friends for second-degree intros</li>
        </ol>

        <p>
          <strong>Free</strong> for personal use.{" "}
          <strong>
            <a href={GITHUB_REPO_URL} className="no-underline hover:underline">
              Open source
            </a>
          </strong>
          {" "}— your data stays yours. Export or delete anytime.
        </p>

        <p>
          <Button asChild size="sm">
            <Link href="/login">Get started</Link>
          </Button>
        </p>

        <p>
          Also works as an MCP server for Claude, ChatGPT, and Gemini (via{" "}
          <a href={mcpPath} className="no-underline hover:underline">
            MCP
          </a>
          ) and terminal agents (via{" "}
          <a href={`${API_BASE}/skill.md`} className="no-underline hover:underline">
            skill.md
          </a>
          ).
        </p>
      </MarketingProse>
    </MarketingMain>
  );
}
