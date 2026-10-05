import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Card shadcn dengan bentuk kartu eutopos: sudut besar, tanpa cincin, isi langsung di dalam kartu. */
export function Panel({ className, ...props }: React.ComponentProps<typeof Card>) {
  return <Card className={cn("min-w-0 gap-3.5 rounded-[var(--radius-card)] p-5 text-base ring-0", className)} {...props} />;
}
