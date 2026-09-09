export const metadata = {
  title: "Мои сделки",
  robots: { index: false, follow: false },
};

export default function CabinetLayout({ children }: { children: React.ReactNode }) {
  return <div className="cabinet-v3">{children}</div>;
}
