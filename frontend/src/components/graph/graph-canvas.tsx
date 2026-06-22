"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useMemo } from "react";

import "@xyflow/react/dist/style.css";

import { layoutGraph } from "@/components/graph/layout";
import { MemoryNode, type MemoryNodeData } from "@/components/graph/memory-node";
import { EDGE_STYLES } from "@/lib/constants";
import type { GraphEdge, GraphNode } from "@/types/graph";

const NODE_TYPES = { memory: MemoryNode };

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  rootId?: string | null;
  onNodeClick?: (nodeId: string) => void;
  onEdgeClick?: (edge: GraphEdge) => void;
}

export function GraphCanvas({ nodes, edges, rootId, onNodeClick, onEdgeClick }: GraphCanvasProps) {
  const edgeById = useMemo(() => {
    const map = new Map<string, GraphEdge>();
    edges.forEach((e) => map.set(`${e.source_id}-${e.target_id}-${e.edge_type}`, e));
    return map;
  }, [edges]);

  const { rfNodes, rfEdges } = useMemo(() => {
    const mappedNodes: Node[] = nodes.map((node) => ({
      id: node.node_id,
      type: "memory",
      position: { x: 0, y: 0 },
      data: {
        label: String(node.properties.content ?? node.label),
        nodeType: node.node_type,
        isRoot: node.node_id === rootId,
      } satisfies MemoryNodeData,
    }));

    const mappedEdges: Edge[] = edges.map((edge) => {
      const style = EDGE_STYLES[edge.edge_type];
      return {
        id: `${edge.source_id}-${edge.target_id}-${edge.edge_type}`,
        source: edge.source_id,
        target: edge.target_id,
        label: style.label,
        labelStyle: { fontSize: 10, fill: style.color },
        style: {
          stroke: style.color,
          strokeWidth: 1.5,
          strokeDasharray: style.dashed ? "5 4" : undefined,
        },
        markerEnd: style.directed
          ? { type: MarkerType.ArrowClosed, color: style.color }
          : undefined,
      };
    });

    return {
      rfNodes: layoutGraph(mappedNodes, mappedEdges),
      rfEdges: mappedEdges,
    };
  }, [nodes, edges, rootId]);

  return (
    <div className="h-[600px] w-full overflow-hidden rounded-lg border bg-card">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        onEdgeClick={(_, edge) => {
          const found = edgeById.get(edge.id);
          if (found) onEdgeClick?.(found);
        }}
      >
        <Background />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable className="!hidden md:!block" />
      </ReactFlow>
    </div>
  );
}
