import type { Metadata } from "next";
import { CompatibilityTool } from "@/components/compatibility/CompatibilityTool";
export const metadata: Metadata = { title: "Совместимость артиста и площадки · Букер", robots: { index: false } };
export default function Page() { return <CompatibilityTool />; }
