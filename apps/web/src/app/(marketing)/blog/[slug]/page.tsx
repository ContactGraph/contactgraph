import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { MarketingMain, MarketingProse } from "../../components/marketing-prose";
import {
  blogPageHref,
  formatBlogDate,
  getAllSlugs,
  getPostBySlug,
  type BlogPost,
} from "@/lib/blog";

export function generateStaticParams(): { slug: string }[] {
  return getAllSlugs().map((slug: string) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post: BlogPost | undefined = getPostBySlug(slug);
  if (!post) {
    return {};
  }

  return {
    title: `${post.title} — ContactGraph`,
    description: post.description,
    alternates: { canonical: blogPageHref(post.slug) },
    openGraph: {
      title: post.title,
      description: post.description,
      type: "article",
      siteName: "ContactGraph",
      locale: "en_US",
      publishedTime: post.date,
      authors: [post.author],
    },
    twitter: {
      card: "summary",
      title: post.title,
      description: post.description,
    },
  };
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post: BlogPost | undefined = getPostBySlug(slug);
  if (!post) {
    notFound();
  }

  return (
    <MarketingMain wide>
      <MarketingProse>
        <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          <Link href="/blog" className="no-underline hover:underline">
            Blog
          </Link>
          {" · "}
          {formatBlogDate(post.date)} · {post.author}
        </p>
        <h1>{post.title}</h1>
        {post.image ? (
          <img
            src={post.image}
            alt=""
            className="mb-6 w-full rounded-md object-cover"
            style={{ aspectRatio: "2/1" }}
          />
        ) : null}
        <div dangerouslySetInnerHTML={{ __html: post.html }} />
      </MarketingProse>
    </MarketingMain>
  );
}
