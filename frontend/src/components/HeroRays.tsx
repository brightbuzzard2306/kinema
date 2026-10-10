"use client";

import dynamic from "next/dynamic";
import { useSyncExternalStore } from "react";

// ogl (WebGL) is loaded only in the browser, only on the hero, and only when the device can render it.
const LightRays = dynamic(() => import("./bits/LightRays"), { ssr: false });

function canRender(): boolean {
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
const noop = () => () => {};

/** A projector beam falling from the top of the hero (React Bits "LightRays"), faded out toward the bottom. */
export function HeroRays() {
  const ok = useSyncExternalStore(noop, canRender, () => false);
  if (!ok) return null;
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 h-[92vh] opacity-90 [mask-image:linear-gradient(to_bottom,#000_45%,transparent_100%)]"
    >
      <LightRays
        raysOrigin="top-center"
        raysColor="#ffffff"
        raysSpeed={0.55}
        lightSpread={0.7}
        rayLength={1.3}
        followMouse
        mouseInfluence={0.08}
        noiseAmount={0.1}
        distortion={0.04}
        fadeDistance={0.95}
        saturation={0}
      />
    </div>
  );
}
