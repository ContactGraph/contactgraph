import { redirect } from "next/navigation";

import { AdminDashboard } from "@/components/admin/admin-dashboard";
import { getSession } from "@/lib/session";

export default async function AdminPage() {
  const session = await getSession();

  if (!session.isAdmin) {
    redirect("/graph");
  }

  return <AdminDashboard />;
}
