import { MessagesHubClient } from "@/components/MessagesHubClient";

export const metadata = {
  title: "Сообщения площадки",
  robots: { index: false, follow: false },
};

export default function VenueMessagesPage() {
  return <MessagesHubClient backHref="/cabinet/venue" />;
}
