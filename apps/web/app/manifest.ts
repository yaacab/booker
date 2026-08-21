import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Букер",
    short_name: "Букер",
    description: "Слот, цифра с сервера и подписи в одной комнате.",
    start_url: "/",
    display: "standalone",
    background_color: "#F3F0E9",
    theme_color: "#2D6A66",
    lang: "ru",
    shortcuts: [
      { name: "Кто ещё не занят", short_name: "Свободные", url: "/search" },
      { name: "Создать заявку", short_name: "Заявка", url: "/events/new" },
    ],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
