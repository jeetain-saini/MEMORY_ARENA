import { AnimatedNumber } from "@/components/shared/animated-number";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  hint?: string;
  className?: string;
}

export function StatCard({ title, value, hint, className }: StatCardProps) {
  return (
    <Card className={cn("lift relative overflow-hidden", className)}>
      {/* Accent wash in the corner for depth. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 h-24 w-24 rounded-full bg-indigo-500/15 blur-2xl"
      />
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-gradient text-3xl font-semibold tabular-nums">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </div>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
