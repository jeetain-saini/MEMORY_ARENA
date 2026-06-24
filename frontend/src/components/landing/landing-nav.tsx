"use client";

import { Brain, Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface NavLink {
  label: string;
  href: string;
}

// Maps the landing nav to real app routes where they exist.
const NAV_LINKS: NavLink[] = [
  { label: "Home", href: "/" },
  { label: "Memories", href: "/memories" },
  { label: "Knowledge Graph", href: "/graph" },
  { label: "Plans", href: "#plans" },
  { label: "Live Demo", href: "/agent" },
];

export function LandingNav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="hero-fade-up fixed inset-x-0 top-0 z-30 px-5 py-5 sm:px-8">
      <nav className="mx-auto flex max-w-7xl items-center justify-between">
        {/* Left — logo + wordmark */}
        <Link href="/" className="flex items-center gap-2 text-white" aria-label="MemoryArena home">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/20 bg-white/10 backdrop-blur-md">
            <Brain className="h-5 w-5" />
          </span>
          <span className="text-lg font-semibold tracking-tight">MemoryArena</span>
        </Link>

        {/* Center — glassmorphism pill nav (desktop only) */}
        <div className="hidden md:block">
          <ul className="flex items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2 py-1.5 backdrop-blur-xl">
            {NAV_LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  className="rounded-full px-4 py-1.5 text-sm font-medium text-white/80 transition-colors hover:bg-white/15 hover:text-white"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        {/* Right — Sign Up (desktop) + mobile trigger */}
        <div className="flex items-center gap-2">
          <Link
            href="/dashboard"
            className="hidden rounded-full border border-white/20 bg-white px-5 py-2 text-sm font-semibold text-black transition-colors hover:bg-white/90 md:inline-flex"
          >
            Sign Up
          </Link>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/20 bg-white/10 text-white backdrop-blur-md md:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </nav>

      {/* Mobile menu panel */}
      {open ? (
        <div className="mt-3 md:hidden">
          <ul className="space-y-1 rounded-2xl border border-white/15 bg-black/70 p-3 backdrop-blur-xl">
            {NAV_LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-xl px-4 py-2.5 text-sm font-medium text-white/85 transition-colors hover:bg-white/10 hover:text-white"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="/dashboard"
                onClick={() => setOpen(false)}
                className="mt-1 block rounded-xl bg-white px-4 py-2.5 text-center text-sm font-semibold text-black"
              >
                Sign Up
              </Link>
            </li>
          </ul>
        </div>
      ) : null}
    </header>
  );
}
