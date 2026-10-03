import { CabinetProfilePreview } from "@/components/cabinet/CabinetProfilePreview";

export const metadata = {
  title: "Предпросмотр профиля · Букер",
  robots: { index: false, follow: false },
};

// Profile data is fetched only in the browser after checking the signed-in organization.
export default function CabinetProfilePreviewPage() {
  return <CabinetProfilePreview />;
}
