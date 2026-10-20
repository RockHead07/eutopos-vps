/** Aturan nama area untuk halaman New map session. Fungsi murni supaya bisa diuji tanpa browser. */
import { AREA_ID_RE } from "./api";

export const AREA_ID_MAX = 40;
export const AREA_NAME_MAX = 100;

export const AREA_ID_HINT =
  "Lowercase letters, digits and hyphens, up to 40 characters. Example: hcm-lantai10.";
export const AREA_NAME_HINT = "Shown in the dashboard, up to 100 characters.";

export type AreaValidation =
  | { ok: true; value: string }
  | { ok: false; message: string; suggestion?: string };

export function normalizeAreaId(raw: string): string {
  return raw.trim().toLowerCase();
}

export function normalizeAreaName(raw: string): string {
  return raw.trim();
}

export function slugifyAreaId(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, AREA_ID_MAX);
}

function quoteList(chars: string[]): string {
  const quoted = chars.slice(0, 3).map((char) => `"${char}"`);
  if (quoted.length === 1) return quoted[0];
  if (quoted.length === 2) return `${quoted[0]} or ${quoted[1]}`;
  return `${quoted.slice(0, -1).join(", ")} or ${quoted[quoted.length - 1]}`;
}

function invalidAreaId(value: string, message: string): AreaValidation {
  const suggestion = slugifyAreaId(value);
  if (suggestion && suggestion !== value && AREA_ID_RE.test(suggestion)) {
    return { ok: false, message, suggestion };
  }
  return { ok: false, message };
}

export function validateAreaId(raw: string): AreaValidation {
  const value = normalizeAreaId(raw);
  if (!value) return { ok: false, message: "Area ID is required." };
  if (value.length > AREA_ID_MAX) {
    return invalidAreaId(
      value,
      `Area ID is too long (${value.length} of ${AREA_ID_MAX} characters).`,
    );
  }
  if (/\s/.test(value)) {
    return invalidAreaId(value, "Area ID cannot contain spaces.");
  }

  const outside = [...new Set(value.replace(/[a-z0-9-]/g, ""))];
  if (outside.length > 0) {
    return invalidAreaId(value, `Area ID cannot contain ${quoteList(outside)}.`);
  }
  if (value.startsWith("-")) {
    return invalidAreaId(value, "Area ID must start with a letter or digit.");
  }
  if (!AREA_ID_RE.test(value)) {
    return invalidAreaId(
      value,
      "Area ID must start with a lowercase letter or digit and contain only lowercase letters, digits and hyphens.",
    );
  }
  return { ok: true, value };
}

export function validateAreaName(raw: string): AreaValidation {
  const value = normalizeAreaName(raw);
  if (!value) return { ok: false, message: "Area name is required." };
  if (value.length > AREA_NAME_MAX) {
    return {
      ok: false,
      message: `Area name is too long (${value.length} of ${AREA_NAME_MAX} characters).`,
    };
  }
  return { ok: true, value };
}
