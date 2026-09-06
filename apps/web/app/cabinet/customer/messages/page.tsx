import { MessagesHubClient } from "@/components/MessagesHubClient";

export const metadata = {
  title: "Сообщения",
  robots: { index: false, follow: false },
};

export default function CustomerMessagesPage() {
  return <MessagesHubClient backHref="/cabinet/customer" />;
}
