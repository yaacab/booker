'use client';
import Link from 'next/link';
import { useTransition, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
export function CatalogLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <Link href={href} className={className} aria-busy={pending} onClick={event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    startTransition(() => router.push(href));
  }}>{children}{pending && <span role="status"> · Загружаем…</span>}</Link>;
}
