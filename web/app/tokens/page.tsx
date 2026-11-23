"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Panel } from "@/components/Panel";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, formatDate, type AppToken } from "@/lib/api";
import { useLocale, useT } from "@/lib/i18n";
import { PageHead } from "@/lib/PageHead";
import { useSharedPoll } from "@/lib/usePoll";

const TOKEN_NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;

function TokenManager() {
  const t = useT();
  const { locale } = useLocale();
  const [rows, setRows] = useState<AppToken[] | null>(null);
  const [name, setName] = useState("");
  const [issued, setIssued] = useState<{ name: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoke, setRevoke] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.appTokens()
      .then((data) => { if (alive) setRows(data); })
      .catch((err: Error) => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const tokenName = name.trim();
    if (busy || !TOKEN_NAME.test(tokenName)) return;
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      setIssued(await api.createAppToken(tokenName));
      setName("");
      setRows(await api.appTokens());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.token);
      setCopied(true);
      setError(null);
    } catch {
      setError(t("tokens.copyError"));
    }
  }

  async function confirmRevoke() {
    if (!revoke || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.revokeAppToken(revoke);
      if (issued?.name === revoke) setIssued(null);
      setRevoke(null);
      setRows(await api.appTokens());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4">
      <Panel>
        <form onSubmit={create} className="flex flex-wrap items-end gap-3">
          <div className="grid min-w-0 flex-1 gap-1.5 sm:max-w-sm">
            <Label htmlFor="token-name">{t("tokens.name")}</Label>
            <Input
              id="token-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-describedby="token-name-hint"
              autoComplete="off"
              maxLength={40}
              required
            />
          </div>
          <Button type="submit" disabled={busy || !TOKEN_NAME.test(name.trim())}>{t("tokens.create")}</Button>
          <p id="token-name-hint" className="basis-full text-sm text-muted-foreground">{t("tokens.nameHint")}</p>
        </form>
        {issued && (
          <div className="grid gap-2 rounded-lg border border-line bg-muted/50 p-3" aria-live="polite">
            <h2>{t("tokens.reveal", { name: issued.name })}</h2>
            <p className="text-sm text-muted-foreground">{t("tokens.once")}</p>
            <div className="flex flex-wrap items-start gap-2">
              <code className="min-w-0 flex-1 break-all text-sm">{issued.token}</code>
              <Button type="button" variant="outline" onClick={copy}>
                {t(copied ? "tokens.copied" : "tokens.copy")}
              </Button>
            </div>
          </div>
        )}
        {error && !revoke && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </Panel>
      <Panel>
        {rows === null ? !error && <p>{t("tokens.loading")}</p> : !rows.length ? (
          <p className="text-sm text-muted-foreground">{t("tokens.empty")}</p>
        ) : (
          <Table aria-label={t("tokens.title")}>
            <TableHeader>
              <TableRow>
                <TableHead>{t("tokens.name")}</TableHead>
                <TableHead>{t("tokens.status")}</TableHead>
                <TableHead>{t("tokens.createdBy")}</TableHead>
                <TableHead>{t("tokens.created")}</TableHead>
                <TableHead>{t("tokens.lastUsed")}</TableHead>
                <TableHead className="text-right">{t("tokens.revoke")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.name}>
                  <TableCell className="font-medium">{row.name}</TableCell>
                  <TableCell>
                    <Badge variant={row.revoked_at ? "secondary" : "outline"}>
                      {t(row.revoked_at ? "tokens.revoked" : "tokens.active")}
                    </Badge>
                  </TableCell>
                  <TableCell>{row.created_by}</TableCell>
                  <TableCell>{formatDate(row.created_at, locale)}</TableCell>
                  <TableCell>{row.last_used_at ? formatDate(row.last_used_at, locale) : t("tokens.neverUsed")}</TableCell>
                  <TableCell className="text-right">
                    {!row.revoked_at && (
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={busy}
                        aria-label={t("tokens.revokeNamed", { name: row.name })}
                        onClick={() => { setError(null); setRevoke(row.name); }}
                      >
                        {t("tokens.revoke")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
      <AlertDialog open={revoke !== null} onOpenChange={(open) => { if (!open && !busy) setRevoke(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("tokens.revokeNamed", { name: revoke ?? "" })}</AlertDialogTitle>
            <AlertDialogDescription>{t("tokens.revokeMessage")}</AlertDialogDescription>
          </AlertDialogHeader>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t("tokens.cancel")}</AlertDialogCancel>
            <Button type="button" variant="destructive" disabled={busy} onClick={confirmRevoke}>
              {t("tokens.revoke")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default function TokensPage() {
  const t = useT();
  const { data: me, error } = useSharedPoll(api.me, 60_000);
  return (
    <>
      <PageHead crumbs={[{ label: t("nav.tokens") }]} title={t("tokens.title")} />
      {me?.is_admin && !error ? (
        <TokenManager />
      ) : (
        <Panel><p>{error ?? t(me ? "tokens.adminOnly" : "tokens.loading")}</p></Panel>
      )}
    </>
  );
}
