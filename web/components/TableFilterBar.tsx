"use client";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/SearchBar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useT } from "@/lib/i18n";

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
  searchPlaceholder,
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
  const t = useT();

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pb-3.5 mb-2 border-b border-line/60">
      <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[240px]">
        <div className="w-full sm:w-64">
          <SearchBar
            value={search}
            onChange={onSearchChange}
            placeholder={searchPlaceholder || t("filter.searchPlaceholder")}
            variant="compact"
            shortcut={true}
          />
        </div>
        {statusOptions.length > 0 && (
          <div className="w-36">
            <Select value={statusFilter} onValueChange={onStatusChange}>
              <SelectTrigger className="w-full text-xs" aria-label={t("filter.byStatusAria")}>
                <SelectValue placeholder={t("filter.allStatuses")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("filter.allStatuses")}</SelectItem>
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
              <SelectTrigger className="w-full text-xs" aria-label={t("filter.byAreaAria")}>
                <SelectValue placeholder={t("filter.allAreas")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("filter.allAreas")}</SelectItem>
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
          {t("filter.showingCount", { filtered: filteredCount, total: totalCount })}
        </span>
        {isFiltered && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="h-7 px-2 text-xs text-forest hover:text-forest-hover font-medium cursor-pointer"
          >
            {t("filter.reset")}
          </Button>
        )}
      </div>
    </div>
  );
}
