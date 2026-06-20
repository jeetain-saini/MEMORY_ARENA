import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export function JsonViewer({ value, className }: { value: unknown; className?: string }) {
  return (
    <ScrollArea className={cn("max-h-80 rounded-md border bg-muted/40", className)}>
      <pre className="p-3 text-xs leading-relaxed">
        {JSON.stringify(value, null, 2)}
      </pre>
    </ScrollArea>
  );
}
