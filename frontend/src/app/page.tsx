import { LandingHero } from "@/components/landing/landing-hero";

// The MemoryArena landing page owns "/". It renders full-bleed (AppShell skips
// its chrome for this route). The functional dashboard now lives at /dashboard.
export default function HomePage() {
  return <LandingHero />;
}
