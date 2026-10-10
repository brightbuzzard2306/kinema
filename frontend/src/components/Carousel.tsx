"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/** Horizontal snap carousel with glass arrow buttons and a soft edge fade. */
export function Carousel({ children, label, className }: { children: React.ReactNode; label: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setEdge({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 8 });
  }, []);

  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure, children]);

  const scroll = (dir: -1 | 1) => ref.current?.scrollBy({ left: dir * Math.max(240, (ref.current?.clientWidth ?? 600) * 0.8), behavior: "smooth" });

  return (
    <div className={cn("group/carousel relative", className)}>
      <div
        ref={ref}
        onScroll={measure}
        role="region"
        aria-label={label}
        tabIndex={0}
        className="hide-scrollbar fade-mask-x -mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-6 pt-2 [perspective:1200px] sm:-mx-6 sm:px-6"
      >
        {children}
      </div>
      {(["prev", "next"] as const).map((d) => {
        const hidden = d === "prev" ? edge.start : edge.end;
        return (
          <button
            key={d}
            type="button"
            tabIndex={hidden ? -1 : 0}
            aria-label={d === "prev" ? "Scroll left" : "Scroll right"}
            onClick={() => scroll(d === "prev" ? -1 : 1)}
            className={cn(
              "glass-pill press absolute top-[42%] z-10 hidden h-11 w-11 -translate-y-1/2 place-items-center rounded-full text-white transition-opacity md:grid",
              d === "prev" ? "-left-5" : "-right-5",
              hidden ? "pointer-events-none opacity-0" : "opacity-0 group-hover/carousel:opacity-100 focus-visible:opacity-100",
            )}
          >
            {d === "prev" ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          </button>
        );
      })}
    </div>
  );
}
