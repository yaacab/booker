import type { MetadataRoute } from "next";
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: '*', allow: '/', disallow: ['/cabinet', '/admin', '/profile', '/api/', '/login', '/register', '/events', '/deals', '/shortlists', '/share'] }],
    sitemap: 'https://bukergo.ru/sitemap.xml',
    host: 'https://bukergo.ru',
  };
}
