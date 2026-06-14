import type { Metadata } from "next";
import Link from "next/link";

import {
  blogPageHref,
  formatBlogDate,
  getAllPosts,
  type BlogPostSummary,
} from "@/lib/blog";

const PAGE_TITLE = "Blog";
const PAGE_DESCRIPTION =
  "Updates, guides, and stories from the ContactGraph team.";

export const metadata: Metadata = {
  title: `${PAGE_TITLE} — ContactGraph`,
  description: PAGE_DESCRIPTION,
  alternates: { canonical: "/blog" },
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

export default function BlogIndexPage() {
  const posts: readonly BlogPostSummary[] = getAllPosts();

  return (
    <main className="flex-1">
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <SectionLabel>Blog</SectionLabel>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-[2.75rem] sm:leading-[1.1]">
          Notes from ContactGraph
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          Product updates, warm-path job search ideas, and how to connect AI to
          your network safely.
        </p>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
          {posts.length === 0 ? (
            <p className="text-base text-muted-foreground">
              No posts yet. Check back soon.
            </p>
          ) : (
            <ul className="divide-y divide-border border border-border">
              {posts.map((post: BlogPostSummary) => (
                <li key={post.slug}>
                  <Link
                    href={blogPageHref(post.slug)}
                    className="block px-4 py-5 no-underline transition-colors hover:bg-secondary sm:px-6"
                  >
                    <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                      {formatBlogDate(post.date)} · {post.author}
                    </p>
                    <h2 className="mt-1 text-lg font-bold text-foreground">
                      {post.title}
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {post.description}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
