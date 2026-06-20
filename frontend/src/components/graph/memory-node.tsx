"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import { NODE_TYPE_COLORS } from "@/lib/constants";
import type { NodeType } from "@/types/api";

export interface MemoryNodeData {
  label: string;
  nodeType: NodeType;
  isRoot: boolean;
  [key: string]: unknown;
}

/** Custom React Flow node rendering a memory's type + content preview. */
export function MemoryNode({ data }: NodeProps) {
  const d = data as MemoryNodeData;
  const color = NODE_TYPE_COLORS[d.nodeType] ?? NODE_TYPE_COLORS.memory;
  return (
    <div
      className="w-[200px] rounded-md border bg-card px-3 py-2 text-xs shadow-sm"
      style={{ borderColor: color, borderLeftWidth: 4 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />
      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold uppercase tracking-wide" style={{ color }}>
          {d.nodeType}
        </span>
        {d.isRoot ? <span className="text-[10px] text-primary">root</span> : null}
      </div>
      <p className="line-clamp-3 text-foreground/90">{d.label}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  );
}
