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

export function AccountMenu() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

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
    return <div className="ml-auto size-8 rounded-full skeleton shrink-0" aria-label="Loading account" />;
  }

  if (error || !me || !me.email) {
    return null;
  }

  const initial = me.email.split("@")[0]?.charAt(0).toUpperCase() || "?";

  return (
    <div className="ml-auto flex items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="icon-sm"
            className="size-8 rounded-full font-bold select-none cursor-pointer bg-card hover:bg-mist text-ink border-line shrink-0"
            aria-label={`Account menu for ${me.email}`}
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
                Admin
              </Badge>
            )}
          </div>
          {me.email !== "dev@local" && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <a href="/cdn-cgi/access/logout" className="cursor-pointer">
                  Sign out
                </a>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
