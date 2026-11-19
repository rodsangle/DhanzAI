import { redirect } from "next/navigation";

// Each app is managed on the Apps page (S20); old links to /apps/<app> land there.
export default function Page() {
  redirect("/apps");
}
