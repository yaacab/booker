export const metadata = {
  title: "Помощь",
  alternates: { canonical: "/faq" },
};

export default function FaqLayout({ children }: { children: React.ReactNode }) {
  return <div className="v3-shell">{children}</div>;
}
