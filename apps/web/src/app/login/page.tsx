import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { getSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Sign In — ContactGraph",
  description:
    "Sign in to ContactGraph with your Google account. Search your private contact graph, find warm paths to open roles, and share networks with friends.",
  alternates: { canonical: "/login" },
  openGraph: {
    title: "Sign In — ContactGraph",
    description:
      "Sign in to ContactGraph with your Google account. Search your private contact graph, find warm paths to open roles, and share networks with friends.",
    type: "website",
    siteName: "ContactGraph",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: "Sign In — ContactGraph",
    description:
      "Sign in to ContactGraph with your Google account. Search your private contact graph, find warm paths to open roles, and share networks with friends.",
  },
};

export default async function LoginPage() {
  const session = await getSession();
  if (session.isLoggedIn) {
    redirect("/graph");
  }

  return (
    <div className="flex min-h-full flex-1 items-center justify-center px-4 py-16">
      <LoginForm />
    </div>
  );
}
