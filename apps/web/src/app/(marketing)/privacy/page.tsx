import type { Metadata } from "next";

import { MarketingMain, MarketingProse } from "../components/marketing-prose";

export const metadata: Metadata = {
  title: "Privacy Policy — ContactGraph",
  description:
    "How ContactGraph collects, stores, and protects your data. We access only metadata and contact fields — never email bodies — and never sell your information.",
  alternates: { canonical: "/privacy" },
  openGraph: {
    title: "Privacy Policy — ContactGraph",
    description:
      "How ContactGraph collects, stores, and protects your data. We access only metadata and contact fields — never email bodies — and never sell your information.",
    type: "website",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: "Privacy Policy — ContactGraph",
    description:
      "How ContactGraph collects, stores, and protects your data. We access only metadata and contact fields — never email bodies — and never sell your information.",
  },
};

export default function PrivacyPage() {
  return (
    <MarketingMain wide>
      <MarketingProse>
        <h1>Privacy Policy</h1>
        <p><em>Effective: May 25, 2026</em></p>

        <h2>What we collect</h2>
        <p>
          When you connect a data source, ContactGraph accesses
          the data you authorize. Sources may include:
        </p>
        <ul>
          <li><strong>Email</strong> (e.g. Gmail) — message metadata
          such as sender, recipient, subject, and date.</li>
          <li><strong>Contacts</strong> (e.g. Google Contacts,
          Apple Contacts / VCF files) — names, emails, phone
          numbers, organizations, and other contact fields.</li>
          <li><strong>Calendar</strong> (e.g. Google Calendar) —
          event metadata including attendees, titles, and times.</li>
          <li><strong>File uploads</strong> — contact data you
          export and upload directly (CSV, VCF, etc.).</li>
        </ul>
        <p>
          For email sources we access <strong>headers only</strong>;
          we do not read or store email body content or attachments.
          For all sources we collect only the metadata and contact
          fields needed to build your graph.
        </p>

        <h2>How we use it</h2>
        <p>
          Data from connected sources is processed to build your
          private contact graph — people, organizations, relationship
          strength, and employment signals. This graph is queryable
          only by you (or an AI agent acting on your behalf via MCP).
        </p>

        <h2>Storage &amp; retention</h2>
        <p>
          Data is stored in a PostgreSQL database. OAuth tokens are
          encrypted at rest. You may delete your account and all
          associated data at any time by contacting{" "}
          <strong>support@basebase.com</strong>.
        </p>

        <h2>Third-party services</h2>
        <p>
          ContactGraph may call external APIs (e.g. OpenAI, Exa) to
          enrich public profile information. Only non-sensitive
          identifiers (names, public URLs) are sent — never email
          content, OAuth tokens, or uploaded files.
        </p>

        <h2>Sharing</h2>
        <p>
          We do not sell, rent, or share your personal data with
          third parties except as required by law.
        </p>

        <h2>Contact</h2>
        <p>Questions? Email <strong>support@basebase.com</strong>.</p>
      </MarketingProse>
    </MarketingMain>
  );
}
