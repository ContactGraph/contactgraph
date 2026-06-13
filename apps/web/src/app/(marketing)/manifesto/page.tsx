import type { Metadata } from "next";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { MarketingMain, MarketingProse } from "../components/marketing-prose";

export const metadata: Metadata = {
  title: "Manifesto — ContactGraph",
  description:
    "We gave away our relationships to LinkedIn and Facebook. ContactGraph builds a private graph from your own data so your agent can answer who you know.",
  alternates: { canonical: "/manifesto" },
  openGraph: {
    title: "Manifesto — ContactGraph",
    description:
      "We gave away our relationships to LinkedIn and Facebook. ContactGraph builds a private graph from your own data so your agent can answer who you know.",
    type: "article",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: "Manifesto — ContactGraph",
    description:
      "We gave away our relationships to LinkedIn and Facebook. ContactGraph builds a private graph from your own data so your agent can answer who you know.",
  },
};

function parseManifesto(): { title: string; html: string } {
  const markdown: string = readFileSync(
    join(process.cwd(), "content", "manifesto.md"),
    "utf-8",
  );

  const titleMatch: RegExpMatchArray | null = markdown.match(/^# (.+)$/m);
  const pageTitle: string = titleMatch?.[1] ?? "Manifesto";

  const lines: string[] = markdown.trim().split("\n");
  const blocks: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line: string = lines[i].trim();

    if (!line) {
      i++;
      continue;
    }
    if (line.startsWith("# ")) {
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
      i++;
      continue;
    }
    if (line.startsWith("---")) {
      blocks.push("<hr />");
      i++;
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length) {
        const itemLine: string = lines[i].trim();
        if (!itemLine) { i++; continue; }
        if (!/^\d+\.\s/.test(itemLine)) break;
        items.push(`<li>${inlineMarkdown(itemLine.replace(/^\d+\.\s/, ""))}</li>`);
        i++;
      }
      blocks.push(`<ol>${items.join("")}</ol>`);
      continue;
    }
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length) {
        const itemLine: string = lines[i].trim();
        if (!itemLine) { i++; continue; }
        if (!itemLine.startsWith("- ")) break;
        items.push(`<li>${inlineMarkdown(itemLine.slice(2))}</li>`);
        i++;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    const pLines: string[] = [line];
    i++;
    while (i < lines.length) {
      const next: string = lines[i].trim();
      if (!next || next.startsWith("#") || next.startsWith("- ") || /^\d+\.\s/.test(next) || next.startsWith("---")) break;
      pLines.push(next);
      i++;
    }
    blocks.push(`<p>${inlineMarkdown(pLines.join(" "))}</p>`);
  }

  return { title: pageTitle, html: blocks.join("\n") };
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inlineMarkdown(text: string): string {
  let s: string = escapeHtml(text);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  return s;
}

export default function ManifestoPage() {
  const { title, html } = parseManifesto();

  return (
    <MarketingMain wide>
      <MarketingProse>
        <h1>{title}</h1>
        <div dangerouslySetInnerHTML={{ __html: html }} />
      </MarketingProse>
    </MarketingMain>
  );
}
