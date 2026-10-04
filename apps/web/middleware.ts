import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const API = (
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const NOT_FOUND_HTML = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Профиль не найден · Букер</title>
<style>body{margin:0;background:#edf1eb;color:#182019;font:16px/1.5 system-ui,sans-serif}main{max-width:680px;margin:12vh auto;padding:32px}a{color:inherit;font-weight:700}</style></head>
<body><main><p>Букер</p><h1>Профиль не найден</h1><p>Карточка не опубликована или была удалена.</p><a href="/search">Вернуться в каталог</a></main></body></html>`;

export async function middleware(request: NextRequest) {
  const match = request.nextUrl.pathname.match(/^\/(artists|venues)\/([^/]+)$/);
  if (!match) return NextResponse.next();
  const resourceType = match[1] === "artists" ? "artist" : "venue";
  const resourceId = decodeURIComponent(match[2]);
  try {
    const status = await fetch(
      `${API}/catalog/public-status/${resourceType}/${encodeURIComponent(resourceId)}`,
      { cache: "no-store", headers: { Accept: "application/json" } },
    );
    if (status.status === 404) {
      return new NextResponse(NOT_FOUND_HTML, {
        status: 404,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
          "X-Robots-Tag": "noindex, nofollow",
        },
      });
    }
  } catch {
    // Let the server component surface upstream outages as a 5xx.
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/artists/:id", "/venues/:id"],
};
