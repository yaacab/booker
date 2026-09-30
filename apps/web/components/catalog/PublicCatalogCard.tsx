'use client';
import { useEffect, useRef, type ReactNode } from 'react';
import { observeDiscovery } from '@/lib/discovery';
export function PublicCatalogCard({ id, kind, children }: { id: string; kind: 'artist' | 'venue'; children: ReactNode }) {
  const element = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observeDiscovery(kind, id, 'impression');
        observer.disconnect();
      }
    }, { threshold: 0.25 });
    observer.observe(element.current);
    return () => observer.disconnect();
  }, [id, kind]);
  return <article className="card" ref={element}>{children}</article>;
}
