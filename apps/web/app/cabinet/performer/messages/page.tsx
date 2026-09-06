import { MessagesHubClient } from "@/components/MessagesHubClient";

export const metadata = {
  title: "Сообщения исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerMessagesPage() {
  return <MessagesHubClient backHref="/cabinet/performer" />;
}
