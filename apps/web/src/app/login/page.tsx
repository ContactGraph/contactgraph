import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { getSession } from "@/lib/session";

export default async function LoginPage() {
  const session = await getSession();
  if (session.isLoggedIn) {
    redirect("/setup");
  }

  return (
    <div className="flex min-h-full flex-1 items-center justify-center px-4 py-16">
      <LoginForm />
    </div>
  );
}
