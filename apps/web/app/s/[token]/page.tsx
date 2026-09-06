import { SharedShortlistClient } from "@/components/SharedShortlistClient";

export const metadata = {
  title: "Подборка",
  robots: { index: false, follow: false },
};

export default async function SharedShortlistPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <SharedShortlistClient token={token} />;
}
