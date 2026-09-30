import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Букер",
    short_name: "Букер",
    description: "Слот, цифра с сервера и подписи в одной комнате.",
    start_url: "/",
    display: "standalone",
    background_color: "#101112",
    theme_color: "#101112",
    lang: "ru",
    shortcuts: [
      { name: "Открыть каталог", short_name: "Каталог", url: "/search" },
      { name: "Создать заявку", short_name: "Заявка", url: "/events/new" },
    ],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
