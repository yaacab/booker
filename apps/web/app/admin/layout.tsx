export const metadata = {
  title: "Пульт оператора",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className="admin-v3">{children}</div>;
}
