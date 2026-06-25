"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const NAV_LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Architecture", href: "#architecture" },
  { label: "Features", href: "#features" },
  { label: "Docs", href: "#open-source" },
  { label: "GitHub", href: "https://github.com" },
];

export function LandingNav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-colors duration-300 ${
        scrolled
          ? "border-b border-[#CDC8BD] bg-[#ECEAE5]/80 backdrop-blur-md"
          : "border-b border-transparent"
      }`}
    >
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5" aria-label="MemoryArena home">
          <span className="h-7 w-7 rounded-[8px] bg-[#3F7D74]" />
          <span className="font-grotesk text-lg font-semibold tracking-tight text-[#171717]">
            MemoryArena
          </span>
        </Link>

        <ul className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((l) => (
            <li key={l.label}>
              <Link
                href={l.href}
                className="font-spacemono text-xs uppercase tracking-wide text-[#5D5D5D] transition-colors hover:text-[#171717]"
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/agent"
            className="font-spacemono text-xs uppercase tracking-wide text-[#5D5D5D] transition-colors hover:text-[#171717]"
          >
            Demo
          </Link>
          <Link
            href="/dashboard"
            className="rounded-full bg-[#3F7D74] px-4 py-2 font-spacemono text-xs uppercase tracking-wide text-[#F7F5F1] transition-opacity hover:opacity-90"
          >
            Get Started
          </Link>
        </div>

        <button
          type="button"
          aria-label="Toggle menu"
          onClick={() => setOpen((v) => !v)}
          className="text-[#171717] md:hidden"
        >
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </nav>

      {open ? (
        <div className="border-t border-[#CDC8BD] bg-[#ECEAE5] px-5 py-4 md:hidden">
          <ul className="flex flex-col gap-3">
            {[...NAV_LINKS, { label: "Demo", href: "/agent" }, { label: "Get Started", href: "/dashboard" }].map(
              (l) => (
                <li key={l.label}>
                  <Link
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className="font-spacemono text-sm uppercase tracking-wide text-[#171717]"
                  >
                    {l.label}
                  </Link>
                </li>
              ),
            )}
          </ul>
        </div>
      ) : null}
    </header>
  );
}
