'use client';

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export function PageControls({
  page,
  pages,
  onChange,
  chinese,
  label,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
  chinese: boolean;
  label: string;
}) {
  return (
    <nav className="enc-pagination" aria-label={label}>
      <button
        type="button"
        aria-label={`${label} · ${chinese ? '上一页' : 'Previous page'}`}
        disabled={page <= 0}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft size={16} />
      </button>
      <span aria-live="polite">
        {page + 1} / {Math.max(1, pages)}
      </span>
      <button
        type="button"
        aria-label={`${label} · ${chinese ? '下一页' : 'Next page'}`}
        disabled={page >= pages - 1}
        onClick={() => onChange(page + 1)}
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}

/** Browser column fragmentation preserves every word without a nested scrollbar. */
export function PagedReader({
  children,
  chinese,
  label,
}: {
  children: ReactNode;
  chinese: boolean;
  label: string;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const flow = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(1);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      setSize({ width: element.clientWidth, height: element.clientHeight });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    let live = true;
    const measure = () => {
      if (!live || !flow.current || !size.width) return;
      const count = Math.max(
        1,
        Math.round((flow.current.scrollWidth + 24) / (size.width + 24)),
      );
      setPages(count);
      setPage((current) => Math.min(current, count - 1));
    };
    measure();
    void document.fonts.ready.then(measure);
    return () => {
      live = false;
    };
  }, [children, size]);
  return (
    <section className="enc-reader" aria-label={label}>
      <div
        className="enc-reader-viewport"
        ref={viewport}
        onFocusCapture={(event) => {
          if (
            event.target === event.currentTarget ||
            !flow.current ||
            !size.width
          )
            return;
          const offset =
            event.target.getBoundingClientRect().left -
            flow.current.getBoundingClientRect().left;
          setPage(
            Math.max(
              0,
              Math.min(pages - 1, Math.floor(offset / (size.width + 24))),
            ),
          );
          event.currentTarget.scrollLeft = 0;
        }}
      >
        <div
          className="enc-reader-flow"
          ref={flow}
          style={{
            width: size.width || '100%',
            height: size.height || '100%',
            columnWidth: size.width || undefined,
            transform: `translateX(-${page * (size.width + 24)}px)`,
          }}
        >
          {children}
        </div>
      </div>
      <PageControls
        page={page}
        pages={pages}
        onChange={setPage}
        chinese={chinese}
        label={label}
      />
    </section>
  );
}
