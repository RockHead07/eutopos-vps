const STORAGE_KEY = "eutopos.uploadSession";
const SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export type SavedSession = {
  jobId: number;
  key: string;
  areaId: string;
  areaName: string;
  videos: { name: string; size: number; role: string }[];
  urls: Record<string, string>;
  savedAt: number;
};

type FileIdentity = { name: string; size: number; lastModified?: number };

export function fileKey(file: FileIdentity): string {
  return JSON.stringify([file.name, file.size, file.lastModified ?? null]);
}

export function matchUrl(session: SavedSession, file: FileIdentity): string | undefined {
  if (!session.videos.some((video) => video.name === file.name && video.size === file.size)) {
    return undefined;
  }
  return session.urls[fileKey(file)];
}

function isSavedSession(value: unknown): value is SavedSession {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const session = value as Record<string, unknown>;
  if (
    typeof session.jobId !== "number" ||
    !Number.isSafeInteger(session.jobId) ||
    typeof session.key !== "string" ||
    typeof session.areaId !== "string" ||
    typeof session.areaName !== "string" ||
    typeof session.savedAt !== "number" ||
    !Number.isFinite(session.savedAt) ||
    !Array.isArray(session.videos) ||
    session.urls === null ||
    typeof session.urls !== "object" ||
    Array.isArray(session.urls)
  ) {
    return false;
  }

  const videosValid = session.videos.every((video) => {
    if (video === null || typeof video !== "object" || Array.isArray(video)) return false;
    const savedVideo = video as Record<string, unknown>;
    return (
      typeof savedVideo.name === "string" &&
      typeof savedVideo.size === "number" &&
      Number.isFinite(savedVideo.size) &&
      savedVideo.size >= 0 &&
      typeof savedVideo.role === "string"
    );
  });
  const urlsValid = Object.values(session.urls).every((url) => typeof url === "string");
  return videosValid && urlsValid;
}

export function loadSession(now: number): SavedSession | null {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;

  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    clearSession();
    return null;
  }
  if (!isSavedSession(value) || now - value.savedAt > SESSION_MAX_AGE_MS) {
    clearSession();
    return null;
  }

  return {
    jobId: value.jobId,
    key: value.key,
    areaId: value.areaId,
    areaName: value.areaName,
    videos: value.videos.map(({ name, size, role }) => ({ name, size, role })),
    urls: { ...value.urls },
    savedAt: value.savedAt,
  };
}

export function saveSession(session: SavedSession): void {
  try {
    const record: SavedSession = {
      jobId: session.jobId,
      key: session.key,
      areaId: session.areaId,
      areaName: session.areaName,
      videos: session.videos.map(({ name, size, role }) => ({ name, size, role })),
      urls: { ...session.urls },
      savedAt: session.savedAt,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Penyimpanan bisa dimatikan atau tidak tersedia; unggahan tetap jalan di halaman ini.
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Penyimpanan bisa dimatikan atau tidak tersedia.
  }
}
