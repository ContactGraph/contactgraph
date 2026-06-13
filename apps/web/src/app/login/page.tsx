import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { getSession } from "@/lib/session";

export const metadata: Metadata = {
  alternates: { canonical: "/login" },
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
