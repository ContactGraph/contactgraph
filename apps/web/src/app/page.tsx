import type { Metadata } from "next";

import { MarketingHeader } from "./(marketing)/components/marketing-header";
import { MarketingFooter } from "./(marketing)/components/marketing-footer";
import "./(marketing)/marketing.css";

const API_BASE = "https://api.contactgraph.ai";
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

export const metadata: Metadata = {
  title: "ContactGraph — Turn your contacts into a superpower.",
  description:
    "A free, open-source contact graph built from your email, contacts, and calendar — searchable by AI, owned by you.",
  openGraph: {
    title: "ContactGraph — Turn your contacts into a superpower.",
    description:
      "A free, open-source contact graph built from your email, contacts, and calendar — searchable by AI, owned by you.",
    type: "website",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: "ContactGraph — Turn your contacts into a superpower.",
    description:
      "A free, open-source contact graph built from your email, contacts, and calendar — searchable by AI, owned by you.",
  },
};

export default async function HomePage() {
  const mcpPath = `${API_BASE}/mcp`;

  return (
    <div className="marketing-page">
      <MarketingHeader />
      <main className="marketing-content">
        <h1>Turn your contacts into a superpower.</h1>
        <p className="lead">
          Find the people you and your trusted friends already know.
          ContactGraph normalizes, enriches, and indexes your email, contacts,
          and calendar into a private graph you can search by name, company,
          role, or industry — things that are nearly impossible to dig out of
          your inbox directly.
        </p>
        <p className="lead">
          Think of it as an agent-friendly alternative to LinkedIn for
          &ldquo;who do I know?&rdquo; questions — except you own the data, always.
          Download or delete it anytime.
        </p>
        <p className="lead">
          <strong>Agent-first.</strong> No human UI yet — ask your AI assistant
          to set it up. Works with Claude, ChatGPT, and Gemini (via{" "}
          <a href={mcpPath}>MCP</a>) and with OpenClaw
          and similar terminal agents (via{" "}
          <a href={`${API_BASE}/skill.md`}>skill.md</a>).
        </p>
        <p className="lead">
          <strong>Free</strong> for personal use.{" "}
          <strong><a href={GITHUB_REPO_URL}>Open source</a></strong>
          {" "}— contributions welcome.
          We intend to structure ContactGraph as a nonprofit so the graph
          is held in public trust. Social graphs should belong to everyone.
        </p>
      </main>
      <MarketingFooter />
    </div>
  );
}
