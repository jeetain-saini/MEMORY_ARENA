"use client";

import {
  ArrowRight,
  Boxes,
  GitBranch,
  Layers,
  Network,
  Search,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { LandingNav } from "@/components/landing/landing-nav";
import { MemoryNetworkCanvas } from "@/components/landing/memory-network-canvas";

const STATS = [
  { value: "Append-only", label: "Evidence tracking" },
  { value: "Hybrid", label: "Lexical + vector + graph" },
  { value: "Neo4j", label: "Knowledge graph" },
  { value: "Explainable", label: "Confidence evolution" },
];

const FEATURES = [
  {
    icon: Sparkles,
    title: "Semantic memory extraction",
    body: "Durable knowledge is inferred from natural conversation. Raw questions are never stored verbatim.",
  },
  {
    icon: Layers,
    title: "Knowledge consolidation",
    body: "New memories are reinforced, superseded, or reconciled against existing beliefs instead of duplicated.",
  },
  {
    icon: GitBranch,
    title: "Evidence engine",
    body: "Every memory keeps an append-only history of how its confidence and importance evolved, and why.",
  },
  {
    icon: Search,
    title: "Hybrid retrieval",
    body: "Lexical, vector, and graph-expanded signals are fused so related memories surface, not just exact matches.",
  },
  {
    icon: Network,
    title: "Knowledge graph",
    body: "Memories and their typed relationships live in Neo4j, traversable and inspectable.",
  },
  {
    icon: Boxes,
    title: "Explainable memory",
    body: "Answers report the exact memories, summaries, and graph nodes used — no fabricated citations.",
  },
];

const PIPELINE = [
  "Conversation",
  "Inference",
  "Extraction",
  "Consolidation",
  "PostgreSQL",
  "Neo4j",
  "Summaries",
  "Retrieval",
  "Agent response",
];

const TECH = ["FastAPI", "Next.js", "PostgreSQL", "Neo4j", "Redis", "LangGraph", "Docker", "TypeScript"];

function Badge({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-[#CDC8BD] bg-[#F7F5F1] px-3 py-1 font-spacemono text-[11px] uppercase tracking-wide text-[#5D5D5D]">
      {children}
    </span>
  );
}

export function LandingHero() {
  return (
    <div className="font-grotesk min-h-screen bg-[#ECEAE5] text-[#171717]">
      <LandingNav />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          <MemoryNetworkCanvas />
        </div>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(60% 50% at 50% 0%, rgba(236,234,229,0), rgba(236,234,229,0.85) 80%)",
          }}
        />
        <div className="relative mx-auto max-w-6xl px-5 pb-24 pt-40 sm:px-8">
          <Badge>Persistent memory infrastructure</Badge>
          <h1 className="mt-6 max-w-3xl text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            Persistent Memory for AI Agents.
          </h1>
          <p className="mt-4 text-2xl font-medium text-[#5D5D5D] sm:text-3xl">
            Explainable. Searchable. Built to evolve.
          </p>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-[#5D5D5D]">
            MemoryArena enables AI agents to extract, consolidate, reinforce, and retrieve long-term
            knowledge instead of relying only on conversation history.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-full bg-[#3F7D74] px-5 py-3 font-spacemono text-xs uppercase tracking-wide text-[#F7F5F1] transition-opacity hover:opacity-90"
            >
              Explore Platform <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="https://github.com"
              className="inline-flex items-center gap-2 rounded-full border border-[#CDC8BD] bg-[#F7F5F1] px-5 py-3 font-spacemono text-xs uppercase tracking-wide text-[#171717] transition-colors hover:border-[#3F7D74]"
            >
              GitHub
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section id="platform" className="border-y border-[#CDC8BD] bg-[#F7F5F1]">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px px-5 sm:px-8 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="px-4 py-8">
              <div className="font-spacemono text-2xl font-bold text-[#3F7D74]">{s.value}</div>
              <div className="mt-1 font-spacemono text-xs uppercase tracking-wide text-[#5D5D5D]">
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <Badge>Capabilities</Badge>
        <h2 className="mt-5 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
          A memory layer that is durable, self-correcting, and explainable.
        </h2>
        <div className="mt-12 grid grid-cols-1 gap-px overflow-hidden rounded-[20px] border border-[#CDC8BD] bg-[#CDC8BD] sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="group bg-[#F7F5F1] p-7 transition-colors hover:bg-[#F2F0EB]">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] bg-[#3F7D74]/10 text-[#3F7D74]">
                <f.icon className="h-5 w-5" />
              </span>
              <h3 className="mt-5 text-lg font-semibold tracking-tight">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5D5D5D]">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Architecture pipeline */}
      <section id="architecture" className="border-y border-[#CDC8BD] bg-[#F7F5F1]">
        <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
          <Badge>Architecture</Badge>
          <h2 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">
            The memory lifecycle.
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#5D5D5D]">
            Conversation turns flow through inference and consolidation into durable storage, then
            synchronize to the graph and summaries for hybrid retrieval.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-2">
            {PIPELINE.map((step, i) => (
              <span key={step} className="flex items-center gap-2">
                {i > 0 ? <ArrowRight className="h-4 w-4 text-[#3F7D74]" /> : null}
                <span className="rounded-[12px] border border-[#CDC8BD] bg-[#ECEAE5] px-3.5 py-2 font-spacemono text-xs text-[#171717]">
                  {step}
                </span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <Badge>Built with</Badge>
        <h2 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Technical foundation.</h2>
        <div className="mt-10 flex flex-wrap gap-3">
          {TECH.map((t) => (
            <span
              key={t}
              className="rounded-[12px] border border-[#CDC8BD] bg-[#F7F5F1] px-4 py-2.5 font-spacemono text-sm text-[#171717]"
            >
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* Open source / footer */}
      <section id="open-source" className="border-t border-[#CDC8BD] bg-[#F7F5F1]">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
          <div className="rounded-[22px] border border-[#CDC8BD] bg-[#ECEAE5] p-10">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Open source.</h2>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-[#5D5D5D]">
              MemoryArena is MIT-licensed. Read the architecture, run it locally with Docker Compose,
              and contribute.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="https://github.com"
                className="rounded-full bg-[#3F7D74] px-5 py-3 font-spacemono text-xs uppercase tracking-wide text-[#F7F5F1] transition-opacity hover:opacity-90"
              >
                View on GitHub
              </Link>
              <Link
                href="/dashboard"
                className="rounded-full border border-[#CDC8BD] bg-[#F7F5F1] px-5 py-3 font-spacemono text-xs uppercase tracking-wide text-[#171717] transition-colors hover:border-[#3F7D74]"
              >
                Open the app
              </Link>
            </div>
          </div>

          <footer className="mt-14 flex flex-col items-start justify-between gap-6 border-t border-[#CDC8BD] pt-8 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2.5">
              <span className="h-6 w-6 rounded-[7px] bg-[#3F7D74]" />
              <span className="font-grotesk font-semibold tracking-tight">MemoryArena</span>
            </div>
            <ul className="flex flex-wrap gap-6 font-spacemono text-xs uppercase tracking-wide text-[#5D5D5D]">
              {["Documentation", "GitHub", "Architecture", "License", "Contact"].map((l) => (
                <li key={l}>
                  <Link href="#" className="transition-colors hover:text-[#171717]">
                    {l}
                  </Link>
                </li>
              ))}
            </ul>
          </footer>
        </div>
      </section>
    </div>
  );
}
