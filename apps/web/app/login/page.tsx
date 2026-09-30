import AuthPage from "@/components/AuthPage";
import { isPublicRegistrationEnabled } from "@/lib/publicRegistration";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return <AuthPage publicRegistrationEnabled={isPublicRegistrationEnabled()} />;
}
