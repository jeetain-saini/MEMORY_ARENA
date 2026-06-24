"use client";

import { useEffect, useRef } from "react";

// Spotlight radius in px (matches the design spec).
const SPOTLIGHT_R = 260;
// Cursor-follow smoothing factor (per-frame lerp toward the real pointer).
const SMOOTHING = 0.1;

interface SpotlightRevealProps {
  /** Always-visible base image (the "surface"). */
  baseSrc: string;
  /** Image revealed inside the spotlight (the "hidden memory network"). */
  revealSrc: string;
}

/**
 * Dual-image cursor spotlight.
 *
 * Performance: the design spec's literal approach paints the mask onto a
 * <canvas> and reads it back via `canvas.toDataURL()` every frame. That forces
 * a GPU→CPU readback + base64 re-encode each frame, which janks well below
 * 60 FPS. We instead drive a CSS `radial-gradient` mask on the reveal layer and
 * update only its position each frame. The mask stays on the compositor (no
 * readback, no React re-render — we write to the DOM node via a ref), so it
 * holds 60 FPS while producing the identical soft-falloff spotlight.
 */
export function SpotlightReveal({ baseSrc, revealSrc }: SpotlightRevealProps) {
  const revealRef = useRef<HTMLDivElement | null>(null);
  const mouse = useRef({ x: 0, y: 0 });
  const smooth = useRef({ x: 0, y: 0 });
  const rafId = useRef<number | null>(null);

  useEffect(() => {
    const el = revealRef.current;
    if (!el) return;

    const applyMask = (x: number, y: number) => {
      // Opaque core (shows the reveal image) with a soft transparent falloff.
      const mask = `radial-gradient(circle ${SPOTLIGHT_R}px at ${x}px ${y}px, #000 0%, #000 55%, rgba(0,0,0,0) 100%)`;
      el.style.webkitMaskImage = mask;
      el.style.maskImage = mask;
    };

    // Start centered so the reveal is visible before the first pointer move.
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    mouse.current = { x: cx, y: cy };
    smooth.current = { x: cx, y: cy };
    applyMask(cx, cy);

    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Reduced motion: keep a static, centered spotlight — no tracking loop.
    if (reduceMotion) return;

    const onMove = (e: MouseEvent) => {
      mouse.current.x = e.clientX;
      mouse.current.y = e.clientY;
    };
    window.addEventListener("mousemove", onMove, { passive: true });

    const tick = () => {
      smooth.current.x += (mouse.current.x - smooth.current.x) * SMOOTHING;
      smooth.current.y += (mouse.current.y - smooth.current.y) * SMOOTHING;
      applyMask(smooth.current.x, smooth.current.y);
      rafId.current = requestAnimationFrame(tick);
    };
    rafId.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      if (rafId.current !== null) cancelAnimationFrame(rafId.current);
    };
  }, []);

  return (
    <>
      {/* Layer 1 — base image (subtle load zoom). */}
      <div
        className="hero-zoom absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: `url("${baseSrc}")` }}
        aria-hidden
      />
      {/* Layer 2 — reveal image, masked to the spotlight. */}
      <div
        ref={revealRef}
        className="hero-reveal absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: `url("${revealSrc}")`,
          WebkitMaskRepeat: "no-repeat",
          maskRepeat: "no-repeat",
        }}
        aria-hidden
      />
      {/* Legibility overlay for the headings/nav above. */}
      <div
        className="absolute inset-0 bg-gradient-to-b from-black/50 via-black/25 to-black/80"
        aria-hidden
      />
    </>
  );
}
