import { redirect } from "next/navigation";

export default function EmailSyncRedirect() {
  redirect("/dashboard/settings/integrations");
}
