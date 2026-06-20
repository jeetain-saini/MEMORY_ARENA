import Dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_W = 200;
const NODE_H = 64;

/** Lay out React Flow nodes/edges top-down with dagre (good for dependency chains). */
export function layoutGraph(nodes: Node[], edges: Edge[]): Node[] {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 70 });

  nodes.forEach((node) => g.setNode(node.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((edge) => g.setEdge(edge.source, edge.target));

  Dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
    };
  });
}
