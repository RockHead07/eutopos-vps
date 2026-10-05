"use client";
import { TableHead } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";

export type SortDirection = "asc" | "desc";

interface SortableHeadProps {
  column: string;
  label: string;
  activeKey: string | null;
  direction: SortDirection;
  onSort: (column: string) => void;
  className?: string;
}

export function SortableHead({
  column,
  label,
  activeKey,
  direction,
  onSort,
  className = "",
}: SortableHeadProps) {
  const isActive = activeKey === column;
  const iconName = isActive ? (direction === "asc" ? "sort-asc" : "sort-desc") : "sort";

  return (
    <TableHead
      aria-sort={isActive ? (direction === "asc" ? "ascending" : "descending") : "none"}
      className={`text-left select-none ${className}`}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1.5 text-left font-medium text-foreground hover:text-ink transition-colors group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded py-1 -my-1 cursor-pointer"
      >
        <span>{label}</span>
        <span
          className={`inline-flex items-center transition-opacity ${
            isActive ? "text-forest opacity-100 font-bold" : "opacity-40 group-hover:opacity-75"
          }`}
        >
          <Icon name={iconName} />
        </span>
      </button>
    </TableHead>
  );
}
