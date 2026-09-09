export const metadata = {
  title: "Deal Room",
  robots: { index: false, follow: false },
};

export default function DealLayout({ children }: { children: React.ReactNode }) {
  return <div className="v3-shell deal-v3">{children}</div>;
}
