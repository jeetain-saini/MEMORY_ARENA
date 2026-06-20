import type { GraphEdgeType, MemoryStatus, MemoryType, NodeType } from "@/types/api";

export interface GraphNode {
  node_id: string;
  node_type: NodeType;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  edge_type: GraphEdgeType;
  weight: number;
  properties: Record<string, unknown>;
}

export interface GraphMemoryView {
  node: GraphNode | null;
  neighbors: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphTraversalResult {
  root_id: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphSearchRequest {
  query: string;
  user_id: string;
  top_k?: number;
  expand_depth?: number;
}

export interface ExpandedMemory {
  memory_id: string;
  content: string;
  memory_type: MemoryType;
  status: MemoryStatus;
  score: number;
  provenance: string;
  source_memory_id?: string | null;
}

export interface GraphAwareResult {
  query: string;
  user_id: string;
  hybrid_count: number;
  graph_count: number;
  results: ExpandedMemory[];
}
