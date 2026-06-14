import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import matter from "gray-matter";
import { remark } from "remark";
import remarkHtml from "remark-html";

export interface BlogPostFrontmatter {
  readonly title: string;
  readonly slug: string;
  readonly date: string;
  readonly description: string;
  readonly author: string;
}

export interface BlogPostSummary extends BlogPostFrontmatter {}

export interface BlogPost extends BlogPostSummary {
  readonly html: string;
}

const BLOG_DIR: string = join(process.cwd(), "content", "blog");

function isBlogPostFrontmatter(data: unknown): data is BlogPostFrontmatter {
  if (typeof data !== "object" || data === null) {
    return false;
  }

  const record: Record<string, unknown> = data as Record<string, unknown>;
  return (
    typeof record.title === "string" &&
    typeof record.slug === "string" &&
    typeof record.date === "string" &&
    typeof record.description === "string" &&
    typeof record.author === "string"
  );
}

function getMarkdownFilenames(): readonly string[] {
  try {
    return readdirSync(BLOG_DIR).filter((filename: string) =>
      filename.endsWith(".md"),
    );
  } catch {
    return [];
  }
}

function markdownToHtml(markdown: string): string {
  const result = remark().use(remarkHtml).processSync(markdown);
  return String(result);
}

function parseBlogPostFile(filename: string): BlogPost {
  const filePath: string = join(BLOG_DIR, filename);
  const raw: string = readFileSync(filePath, "utf-8");
  const { data, content } = matter(raw);

  if (!isBlogPostFrontmatter(data)) {
    throw new Error(`Invalid frontmatter in ${filename}`);
  }

  const html: string = markdownToHtml(content);
  return { ...data, html };
}

function toSummary(post: BlogPost): BlogPostSummary {
  return {
    title: post.title,
    slug: post.slug,
    date: post.date,
    description: post.description,
    author: post.author,
  };
}

export function blogPageHref(slug: string): `/blog/${string}` {
  return `/blog/${slug}`;
}

export function getAllPosts(): readonly BlogPostSummary[] {
  const posts: BlogPost[] = getMarkdownFilenames().map(parseBlogPostFile);

  return posts
    .sort(
      (left: BlogPost, right: BlogPost) =>
        new Date(right.date).getTime() - new Date(left.date).getTime(),
    )
    .map(toSummary);
}

export function getPostBySlug(slug: string): BlogPost | undefined {
  for (const filename of getMarkdownFilenames()) {
    const post: BlogPost = parseBlogPostFile(filename);
    if (post.slug === slug) {
      return post;
    }
  }

  return undefined;
}

export function getAllSlugs(): readonly string[] {
  return getAllPosts().map((post: BlogPostSummary) => post.slug);
}

export function formatBlogDate(date: string): string {
  const parsed: Date = new Date(date);
  if (Number.isNaN(parsed.getTime())) {
    return date;
  }

  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
