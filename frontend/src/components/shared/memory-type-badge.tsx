import { Badge } from "@/components/ui/badge";
import { MEMORY_TYPE_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { MemoryType } from "@/types/api";

export function MemoryTypeBadge({ type }: { type: MemoryType }) {
  return (
    <Badge variant="outline" className={cn("capitalize", MEMORY_TYPE_COLORS[type])}>
      {type}
    </Badge>
  );
}
