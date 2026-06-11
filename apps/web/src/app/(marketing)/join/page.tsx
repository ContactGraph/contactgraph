import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Join ContactGraph — You've been invited to share networks",
  description:
    "A friend invited you to ContactGraph. Sign up to share professional networks — see who each other knows (names and roles only, never emails or phone numbers).",
  openGraph: {
    title: "You're invited to ContactGraph",
    description:
      "A friend wants to share their professional network with you. See who each other knows — names and roles only, never emails or phone numbers.",
    siteName: "ContactGraph",
    type: "website",
    url: "https://contactgraph.ai/join",
  },
  twitter: {
    card: "summary",
    title: "You're invited to ContactGraph",
    description:
      "A friend wants to share their professional network with you. See who each other knows — names and roles only, never emails or phone numbers.",
  },
};

export default function JoinPage() {
  return (
    <main className="mx-auto flex max-w-lg flex-col items-center gap-8 px-4 py-20 text-center">
      <h1 className="text-3xl font-bold tracking-tight">
        You&rsquo;ve been invited to ContactGraph
      </h1>
      <p className="text-lg text-muted-foreground">
        A friend wants to share their professional network with you. Once you
        sign up, you&rsquo;ll both be able to see who each other knows — names
        and roles only, never emails or phone numbers.
      </p>
      <Link
        href="/login"
        className="inline-flex h-10 items-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground no-underline hover:bg-primary/90"
      >
        Sign up &amp; accept invite
      </Link>
      <p className="text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>{" "}
        and check your Graph Sharing tab.
      </p>
    </main>
  );
}
