import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getSession } from "@/lib/session";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();

  if (!session.isLoggedIn || !session.email) {
    redirect("/login");
  }

  return <AppShell email={session.email}>{children}</AppShell>;
}
