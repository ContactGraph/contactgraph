import { redirect } from "next/navigation";

import { getSession } from "@/lib/session";

export default async function HomePage() {
  const session = await getSession();
  redirect(session.isLoggedIn ? "/people" : "/login");
}
