import { redirect } from "next/navigation";

export default function DealDemoRedirect() {
  redirect("/events/new");
}
