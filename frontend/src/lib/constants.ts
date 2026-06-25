import type { GraphEdgeType, MemoryStatus, MemoryType, NodeType } from "@/types/api";

export const USER_ID_STORAGE_KEY = "memoryarena.userId";

export interface NavItem {
  href: string;
  label: string;
  icon: string; // lucide icon name
}

export const NAV_ITEMS: NavItem[] = [
  // Dashboard moved off "/" so the landing page can own the root route.
  { href: "/dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/timeline", label: "Memory Timeline", icon: "History" },
  { href: "/memories", label: "Memory Explorer", icon: "Database" },
  { href: "/graph", label: "Graph Explorer", icon: "Share2" },
  { href: "/context", label: "Context Playground", icon: "Layers" },
  { href: "/agent", label: "Agent Playground", icon: "Bot" },
  { href: "/summaries", label: "Summary Explorer", icon: "ScrollText" },
];

// Badge color classes per memory type (Tailwind utility strings).
// Translucent, dark-theme-friendly badge palettes (tinted glass pills).
export const MEMORY_TYPE_COLORS: Record<MemoryType, string> = {
  fact: "bg-blue-500/15 text-blue-700 border-blue-400/25",
  goal: "bg-purple-500/15 text-purple-700 border-purple-400/25",
  preference: "bg-pink-500/15 text-pink-700 border-pink-400/25",
  skill: "bg-emerald-500/15 text-emerald-700 border-emerald-400/25",
  project: "bg-amber-500/15 text-amber-700 border-amber-400/25",
  experience: "bg-cyan-500/15 text-cyan-700 border-cyan-400/25",
};

export const STATUS_COLORS: Record<MemoryStatus, string> = {
  active: "bg-green-500/15 text-green-700 border-green-400/25",
  archived: "bg-gray-500/15 text-gray-700 border-gray-400/20",
  superseded: "bg-purple-500/15 text-purple-700 border-purple-400/25",
  forgotten: "bg-amber-500/15 text-amber-700 border-amber-400/25",
  deleted: "bg-red-500/15 text-red-700 border-red-400/25",
};

// Graph edge styling (stroke color + whether it is dashed / directed).
export interface EdgeStyle {
  color: string;
  label: string;
  dashed: boolean;
  directed: boolean;
}

export const EDGE_STYLES: Record<GraphEdgeType, EdgeStyle> = {
  related_to: { color: "#94a3b8", label: "Related to", dashed: false, directed: false },
  supports: { color: "#22c55e", label: "Supports", dashed: false, directed: true },
  used_in: { color: "#0ea5e9", label: "Used in", dashed: false, directed: true },
  depends_on: { color: "#f59e0b", label: "Depends on", dashed: false, directed: true },
  derived_from: { color: "#8b5cf6", label: "Derived from", dashed: false, directed: true },
  reinforces: { color: "#14b8a6", label: "Reinforces", dashed: false, directed: false },
  contradicts: { color: "#ef4444", label: "Contradicts", dashed: true, directed: false },
  supersedes: { color: "#a855f7", label: "Supersedes", dashed: false, directed: true },
  promoted_from: { color: "#ec4899", label: "Promoted from", dashed: false, directed: true },
  cluster_member: { color: "#64748b", label: "Cluster", dashed: true, directed: false },
};

export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  fact: "#3b82f6",
  goal: "#a855f7",
  preference: "#ec4899",
  skill: "#10b981",
  project: "#f59e0b",
  memory: "#64748b",
};

export const SUMMARY_SCOPES: MemoryType[] = ["project", "goal", "experience"];
