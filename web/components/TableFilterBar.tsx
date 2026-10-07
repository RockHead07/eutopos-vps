"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Option {
  value: string;
  label: string;
}

interface TableFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  statusFilter: string;
  onStatusChange: (value: string) => void;
  statusOptions: Option[];
  areaFilter: string;
  onAreaChange: (value: string) => void;
  areaOptions: string[];
  totalCount: number;
  filteredCount: number;
  onReset: () => void;
}

export function TableFilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Search...",
  statusFilter,
  onStatusChange,
  statusOptions,
  areaFilter,
  onAreaChange,
  areaOptions,
  totalCount,
  filteredCount,
  onReset,
}: TableFilterBarProps) {
  const isFiltered = Boolean(search.trim() || statusFilter !== "all" || areaFilter !== "all");

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pb-3.5 mb-2 border-b border-line/60">
      <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[240px]">
        <div className="w-full sm:w-64">
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="h-9 text-xs bg-card"
          />
        </div>
        {statusOptions.length > 0 && (
          <div className="w-36">
            <Select value={statusFilter} onValueChange={onStatusChange}>
              <SelectTrigger className="w-full text-xs" aria-label="Filter by status">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {statusOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {areaOptions.length > 0 && (
          <div className="w-36">
            <Select value={areaFilter} onValueChange={onAreaChange}>
              <SelectTrigger className="w-full text-xs" aria-label="Filter by area">
                <SelectValue placeholder="All areas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All areas</SelectItem>
                {areaOptions.map((area) => (
                  <SelectItem key={area} value={area}>
                    {area}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground ml-auto">
        <span>
          Showing {filteredCount} of {totalCount}
        </span>
        {isFiltered && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="h-7 px-2 text-xs text-forest hover:text-forest-hover font-medium"
          >
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}
