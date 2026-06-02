import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — ContactGraph",
  description:
    "ContactGraph terms of service — usage terms, responsibilities, and disclaimers.",
  openGraph: {
    title: "Terms of Service — ContactGraph",
    description:
      "ContactGraph terms of service — usage terms, responsibilities, and disclaimers.",
    type: "website",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: "Terms of Service — ContactGraph",
    description:
      "ContactGraph terms of service — usage terms, responsibilities, and disclaimers.",
  },
};

export default function TermsPage() {
  return (
    <main className="marketing-content-wide">
      <article className="prose">
        <h1 className="doc-title">TERMS OF SERVICE</h1>
        <p><em>Effective: May 25, 2026</em></p>

        <h2>Acceptance</h2>
        <p>
          By using ContactGraph (&ldquo;the Service&rdquo;), you agree to these terms.
          If you do not agree, do not use the Service.
        </p>

        <h2>Description of service</h2>
        <p>
          ContactGraph is an agent-native personal contact graph.
          It connects to data sources you authorize (email,
          contacts, calendar, file uploads, and others as added),
          builds a private relationship graph, and exposes MCP
          tools for querying your network.
        </p>

        <h2>Your responsibilities</h2>
        <ul>
          <li>You must have the right to grant access to, or
          upload, any data source you connect.</li>
          <li>You are responsible for the security of your
          account credentials and OAuth tokens.</li>
          <li>You agree not to use the Service for unlawful
          purposes or to violate others&apos; privacy.</li>
        </ul>

        <h2>Intellectual property</h2>
        <p>
          The ContactGraph source code is licensed under the{" "}
          <a href="https://github.com/ContactGraph/contactgraph/blob/main/LICENSE">
            Apache License 2.0
          </a>.
          Your data remains yours.
        </p>

        <h2>Disclaimers</h2>
        <p>
          The Service is provided <strong>&ldquo;as is&rdquo;</strong> without warranties
          of any kind. We do not guarantee accuracy of inferred relationships,
          employment data, or enrichment results.
        </p>

        <h2>Limitation of liability</h2>
        <p>
          To the fullest extent permitted by law, ContactGraph and its
          contributors shall not be liable for any indirect, incidental,
          or consequential damages arising from your use of the Service.
        </p>

        <h2>Changes</h2>
        <p>
          We may update these terms. Continued use after changes constitutes
          acceptance. Material changes will be noted on this page.
        </p>

        <h2>Contact</h2>
        <p>Questions? Email <strong>support@basebase.com</strong>.</p>
      </article>
    </main>
  );
}
