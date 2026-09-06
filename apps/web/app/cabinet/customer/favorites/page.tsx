import { FavoritesListClient } from "@/components/FavoritesListClient";

export const metadata = {
  title: "Избранное",
  robots: { index: false, follow: false },
};

export default function CustomerFavoritesPage() {
  return <FavoritesListClient />;
}
