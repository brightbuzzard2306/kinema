"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { useSpotlight } from "@/lib/spotlight";
import { hash } from "@/lib/utils";

const SPOT = 1040; // diameter of the cursor spotlight (a 520px radius, as before)

/**
 * A poster, softened. We draw it into a tiny canvas and let the GPU scale it up smoothly; that gives the same soft wash as a
 * huge CSS blur but costs almost nothing (a full-screen `blur(70px)` is re-rasterised on every hover and is a major source of jank).
 */
function SoftPoster({ src }: { src: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = src;
    return () => {
      cancelled = true;
      img.onload = null;
    };
  }, [src]);
  return <canvas ref={ref} width={64} height={96} aria-hidden className="h-full w-full object-cover" style={{ filter: "grayscale(1)" }} />;
}

/**
 * IMPORTANT - currently OFF on purpose.
 * The <body> has an opaque background that CSS paints on top of this negative-z-index layer, so every effect below
 * (drifting light, cursor glow, hover wash, vignette) has been fully hidden while still costing GPU time and re-renders.
 * Rendering it would also change how the app looks, so it is switched off. To turn the effect on, set
 * NEXT_PUBLIC_IMMERSIVE_BACKDROP=1 in frontend/.env.local AND make <body> transparent (see frontend/README.md).
 */
const BACKDROP_ENABLED = process.env.NEXT_PUBLIC_IMMERSIVE_BACKDROP === "1";

export function Backdrop() {
  return BACKDROP_ENABLED ? <ImmersiveBackdrop /> : null;
}

/**
 * The room. Slow drifting light, a cursor-following spotlight, and - when you hover a movie - the whole
 * backdrop dissolves into that film (its real poster if available, otherwise its generative art).
 * Only transform/opacity change per frame, and hover state is read from its own store so nothing else re-renders.
 */
function ImmersiveBackdrop() {
  const ws = useWorkspaceOptional();
  const spotlight = useSpotlight();
  const posters = ws?.posters ?? {};
  const reduce = useReducedMotion();
  const spot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = spot.current;
    if (!el) return;
    let moved = false;
    const place = (x: number, y: number) => {
      el.style.transform = `translate3d(${x - SPOT / 2}px, ${y - SPOT / 2}px, 0)`;
    };
    const rest = () => place(window.innerWidth * 0.5, window.innerHeight * 0.3); // where it sits before the pointer moves
    rest();
    const onResize = () => !moved && rest();
    window.addEventListener("resize", onResize, { passive: true });
    if (reduce) return () => window.removeEventListener("resize", onResize);

    let raf = 0;
    let nx = 0;
    let ny = 0;
    const move = (e: PointerEvent) => {
      moved = true;
      nx = e.clientX;
      ny = e.clientY;
      if (!raf) {
        raf = requestAnimationFrame(() => {
          raf = 0;
          place(nx, ny);
        });
      }
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
    };
  }, [reduce]);

  const poster = spotlight ? posters[spotlight.movieId] : null;
  const h = spotlight ? hash(spotlight.title) : 0;

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-bg">
      {/* drifting light */}
      <div className="absolute -left-[20%] -top-[30%] h-[80vmax] w-[80vmax] rounded-full opacity-[0.11]" style={{ background: "radial-gradient(closest-side, #fff, transparent)", animation: reduce ? undefined : "drift-a 38s ease-in-out infinite", willChange: "transform" }} />
      <div className="absolute -bottom-[35%] -right-[25%] h-[85vmax] w-[85vmax] rounded-full opacity-[0.08]" style={{ background: "radial-gradient(closest-side, #fff, transparent)", animation: reduce ? undefined : "drift-b 46s ease-in-out infinite", willChange: "transform" }} />
      <div className="absolute left-[30%] top-[35%] h-[55vmax] w-[55vmax] rounded-full opacity-[0.05]" style={{ background: "radial-gradient(closest-side, #fff, transparent)", animation: reduce ? undefined : "drift-c 52s ease-in-out infinite", willChange: "transform" }} />

      {/* hovered film dissolves into the room */}
      <AnimatePresence mode="popLayout">
        {spotlight && (
          <motion.div
            key={spotlight.movieId}
            className="absolute inset-0"
            initial={{ opacity: 0, scale: 1.08 }}
            animate={{ opacity: 1, scale: 1.02 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            style={{ willChange: "opacity, transform" }}
          >
            {poster ? (
              <div className="absolute left-1/2 top-1/2 h-[125vh] w-[125vw] -translate-x-1/2 -translate-y-1/2 opacity-[0.34]">
                <SoftPoster src={poster} />
              </div>
            ) : (
              <div
                className="h-full w-full opacity-70"
                style={{ background: `radial-gradient(70% 60% at ${20 + (h % 60)}% ${25 + ((h >> 5) % 40)}%, rgba(255,255,255,0.16), transparent 70%)` }}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* cursor spotlight: a fixed-size gradient moved with a GPU transform, so moving the mouse never repaints the screen */}
      <div
        ref={spot}
        className="absolute left-0 top-0"
        style={{
          width: SPOT,
          height: SPOT,
          background: "radial-gradient(closest-side, rgba(255,255,255,0.065), transparent 62%)",
          willChange: "transform",
        }}
      />
      {/* vignette */}
      <div className="absolute inset-0" style={{ background: "radial-gradient(130% 90% at 50% 45%, transparent 40%, rgba(0,0,0,0.78) 100%)" }} />
    </div>
  );
}
