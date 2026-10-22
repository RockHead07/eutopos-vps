"use client";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, type Me } from "@/lib/api";
import { LOCALES, useLocale, useT, type TranslationKey } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface SegmentedOption<T extends string> {
  id: T;
  label: string;
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  rounded = false,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (val: T) => void;
  ariaLabel: string;
  rounded?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center border border-line p-0.5",
        rounded ? "rounded-full bg-card shadow-xs" : "rounded-md bg-canvas"
      )}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map(({ id, label }) => {
        const checked = value === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={checked}
            onClick={() => onChange(id)}
            className={cn(
              "px-2 text-xs font-medium transition-colors cursor-pointer flex items-center justify-center max-[959px]:min-w-[44px] max-[959px]:min-h-[44px]",
              rounded ? "rounded-full py-1 min-h-[28px] min-w-[28px]" : "rounded py-0.5 min-h-[24px] min-w-[28px]",
              checked
                ? "bg-foreground text-background font-semibold"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

const THEME_OPTIONS: { id: Theme; labelKey: TranslationKey }[] = [
  { id: "light", labelKey: "theme.light" },
  { id: "dark", labelKey: "theme.dark" },
  { id: "system", labelKey: "theme.system" },
];

function LanguageToggle({ rounded = false }: { rounded?: boolean }) {
  const { locale, setLocale } = useLocale();
  const t = useT();
  return (
    <SegmentedControl
      options={LOCALES}
      value={locale}
      onChange={setLocale}
      ariaLabel={t("account.selectLanguage")}
      rounded={rounded}
    />
  );
}

function ThemeToggle({ rounded = false }: { rounded?: boolean }) {
  const { theme, setTheme } = useTheme();
  const t = useT();
  return (
    <SegmentedControl
      options={THEME_OPTIONS.map(({ id, labelKey }) => ({ id, label: t(labelKey) }))}
      value={theme}
      onChange={setTheme}
      ariaLabel={t("theme.selectTheme")}
      rounded={rounded}
    />
  );
}

export function AccountMenu() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const t = useT();

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((data) => {
        if (alive) {
          setMe(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (alive) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div
        className="size-8 rounded-full skeleton shrink-0"
        aria-label={t("account.loading")}
      />
    );
  }

  // When unauthenticated, show compact language and theme toggles
  if (error || !me || !me.email) {
    return (
      <div className="flex items-center gap-1.5">
        <LanguageToggle rounded />
        <ThemeToggle rounded />
      </div>
    );
  }

  const initial = me.email.split("@")[0]?.charAt(0).toUpperCase() || "?";

  return (
    <div className="flex items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="icon-sm"
            className="size-8 rounded-full font-bold select-none cursor-pointer bg-card hover:bg-mist text-ink border-line shrink-0"
            aria-label={t("account.menuAria", { email: me.email })}
          >
            <span>{initial}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56 p-2">
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
            <span className="font-medium text-foreground truncate" title={me.email}>
              {me.email}
            </span>
            {me.is_admin && (
              <Badge className="h-auto rounded px-1.5 py-0 text-[0.7rem] font-semibold bg-[var(--ok-bg)] text-[var(--ok-fg)] shrink-0">
                {t("account.admin")}
              </Badge>
            )}
          </div>
          <DropdownMenuSeparator />
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
            <span className="text-muted-foreground font-medium">{t("account.language")}</span>
            <LanguageToggle />
          </div>
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
            <span className="text-muted-foreground font-medium">{t("theme.title")}</span>
            <ThemeToggle />
          </div>
          {me.email !== "dev@local" && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <a href="/cdn-cgi/access/logout" className="cursor-pointer">
                  {t("account.signOut")}
                </a>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
