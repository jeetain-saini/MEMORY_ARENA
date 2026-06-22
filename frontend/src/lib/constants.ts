import type { GraphEdgeType, MemoryStatus, MemoryType, NodeType } from "@/types/api";

export const USER_ID_STORAGE_KEY = "memoryarena.userId";

export interface NavItem {
  href: string;
  label: string;
  icon: string; // lucide icon name
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/memories", label: "Memory Explorer", icon: "Database" },
  { href: "/graph", label: "Graph Explorer", icon: "Share2" },
  { href: "/context", label: "Context Playground", icon: "Layers" },
  { href: "/agent", label: "Agent Playground", icon: "Bot" },
  { href: "/summaries", label: "Summary Explorer", icon: "ScrollText" },
];

// Badge color classes per memory type (Tailwind utility strings).
export const MEMORY_TYPE_COLORS: Record<MemoryType, string> = {
  fact: "bg-blue-100 text-blue-800 border-blue-200",
  goal: "bg-purple-100 text-purple-800 border-purple-200",
  preference: "bg-pink-100 text-pink-800 border-pink-200",
  skill: "bg-emerald-100 text-emerald-800 border-emerald-200",
  project: "bg-amber-100 text-amber-800 border-amber-200",
  experience: "bg-cyan-100 text-cyan-800 border-cyan-200",
};

export const STATUS_COLORS: Record<MemoryStatus, string> = {
  active: "bg-green-100 text-green-800 border-green-200",
  archived: "bg-gray-100 text-gray-700 border-gray-200",
  superseded: "bg-purple-100 text-purple-800 border-purple-200",
  forgotten: "bg-amber-100 text-amber-800 border-amber-200",
  deleted: "bg-red-100 text-red-800 border-red-200",
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
