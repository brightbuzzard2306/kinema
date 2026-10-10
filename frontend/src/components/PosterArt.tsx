"use client";

import { useState } from "react";
import { cn, hash } from "@/lib/utils";

const STOP_WORDS = new Set(["the", "a", "an", "of", "and", "in", "to"]);

function initials(title: string): string {
  const words = title.replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter(Boolean);
  const significant = words.filter((w) => !STOP_WORDS.has(w.toLowerCase()));
  const pick = (significant.length ? significant : words).slice(0, 2);
  return pick.map((w) => w[0]).join("").toUpperCase() || "?";
}

/**
 * Real poster when we have one, otherwise a deterministic typographic poster built from the actual
 * title - never a made-up image URL.
 */
export function Poster({
  title,
  year,
  src,
  className,
  eager,
  compact,
}: {
  title: string;
  year: number | null;
  src?: string | null;
  className?: string;
  eager?: boolean;
  /** thumbnail mode: the typographic initials are sized and placed for a tiny box */
  compact?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const h = hash(`${title}${year ?? ""}`);
  const angle = h % 360;
  const gx = 15 + (h % 70);
  const gy = 5 + ((h >> 4) % 45);
  const glow = 0.1 + ((h >> 8) % 12) / 100;
  const lines = 6 + ((h >> 12) % 10);
  const showImage = !!src && !failed;

  return (
    <div className={cn("absolute inset-0 overflow-hidden bg-[#0b0b0c]", className)}>
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background: `radial-gradient(120% 75% at ${gx}% ${gy}%, rgba(255,255,255,${glow}), transparent 58%), linear-gradient(${angle}deg, #1b1b1e 0%, #0a0a0b 70%)`,
        }}
      />
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.07]"
        style={{ backgroundImage: `repeating-linear-gradient(${angle}deg, #fff 0 1px, transparent 1px ${lines * 4}px)` }}
      />
      <span
        aria-hidden
        className={cn(
          "absolute select-none font-display italic leading-none",
          compact ? "inset-0 grid place-items-center text-white/30" : "left-5 top-14 text-white/[0.14]",
        )}
        style={{ fontSize: compact ? "46cqw" : "min(9.5rem, 52cqw)" }}
      >
        {initials(title)}
      </span>
      {showImage && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src!}
          alt={`Poster for ${title}${year ? ` (${year})` : ""}`}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={cn("absolute inset-0 h-full w-full object-cover transition-opacity duration-700", loaded ? "opacity-100" : "opacity-0")}
        />
      )}
    </div>
  );
}
