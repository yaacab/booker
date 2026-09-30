import AuthPage from "@/components/AuthPage";
import { isPublicRegistrationEnabled } from "@/lib/publicRegistration";

export const metadata = { title: "Для артистов — твои будущие выступления" };
export const dynamic = "force-dynamic";

export default function ForArtistsPage() {
  return (
    <AuthPage
      artistWelcome
      publicRegistrationEnabled={isPublicRegistrationEnabled()}
    />
  );
}
