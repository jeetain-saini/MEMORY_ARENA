"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { LandingNav } from "@/components/landing/landing-nav";
import { SpotlightReveal } from "@/components/landing/spotlight-reveal";

// Surface image + the hidden memory-network reveal (shown inside the spotlight).
const BASE_IMAGE =
  "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_195923_b0ba8ace-1d1d-4f2c-9a28-1ab84b330680.png&w=1280&q=85";
const REVEAL_IMAGE =
  "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_201152_bba90a12-bf12-459f-91f0-51f237dbaf3b.png&w=1280&q=85";

export function LandingHero() {
  return (
    <div
      className="min-h-screen bg-white tracking-[-0.02em]"
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      <section
        className="relative w-full overflow-hidden bg-black"
        style={{ height: "100dvh" }}
      >
        {/* Layers 1 + 2 (+ legibility overlay) */}
        <SpotlightReveal baseSrc={BASE_IMAGE} revealSrc={REVEAL_IMAGE} />

        {/* Layer 6 — fixed navigation */}
        <LandingNav />

        {/* Layer 3 — headline + primary CTA */}
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center px-6 sm:px-10">
          <div className="mx-auto w-full max-w-7xl">
            <p
              className="hero-fade-up text-sm font-medium uppercase tracking-[0.25em] text-white/60"
              style={{ animationDelay: "0.15s" }}
            >
              MemoryArena
            </p>
            <h1 className="mt-4 max-w-4xl text-white">
              <span
                className="hero-fade-up block text-5xl font-light leading-[1.05] sm:text-7xl lg:text-8xl"
                style={{ animationDelay: "0.25s" }}
              >
                Memories hold
              </span>
              <span
                className="hero-fade-up font-playfair mt-1 block text-5xl italic leading-[1.05] text-white sm:text-7xl lg:text-8xl"
                style={{ animationDelay: "0.4s" }}
              >
                stories through time
              </span>
            </h1>

            <div
              className="hero-fade-up pointer-events-auto mt-9"
              style={{ animationDelay: "0.55s" }}
            >
              <Link
                href="/memories"
                className="group inline-flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-sm font-semibold text-black shadow-lg shadow-black/20 transition-transform duration-300 ease-premium hover:scale-[1.03]"
              >
                Explore Memory
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
            </div>
          </div>
        </div>

        {/* Layer 4 — bottom-left description */}
        <div className="pointer-events-none absolute bottom-0 left-0 z-20 px-6 pb-8 sm:px-10 sm:pb-10">
          <p
            className="hero-fade-up max-w-xs text-sm leading-relaxed text-white/70"
            style={{ animationDelay: "0.7s" }}
          >
            Move your cursor to reveal the memory network beneath the surface —
            retrieval, recall, and context discovery, layer by layer.
          </p>
        </div>

        {/* Layer 5 — bottom-right content block */}
        <div className="pointer-events-none absolute bottom-0 right-0 z-20 hidden px-10 pb-10 text-right sm:block">
          <div
            className="hero-fade-up ml-auto max-w-xs rounded-2xl border border-white/15 bg-white/10 p-5 backdrop-blur-xl"
            style={{ animationDelay: "0.85s" }}
          >
            <p className="text-xs uppercase tracking-[0.2em] text-white/50">
              Layered recall
            </p>
            <p className="mt-2 text-sm leading-relaxed text-white/80">
              Every memory connects — promotions, clusters, and contradictions
              surface the truth you need, exactly when you need it.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
