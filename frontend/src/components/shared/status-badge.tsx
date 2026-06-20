import { Badge } from "@/components/ui/badge";
import { STATUS_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { MemoryStatus } from "@/types/api";

export function StatusBadge({ status }: { status: MemoryStatus }) {
  return (
    <Badge variant="outline" className={cn("capitalize", STATUS_COLORS[status])}>
      {status}
    </Badge>
  );
}
