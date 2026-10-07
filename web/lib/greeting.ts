/**
 * Pure functions for greeting generation based on local hour, weekday, and user name.
 */

export const GREETINGS = {
  LATE: [
    "Still up, {name}?",
    "Staying up late, {name}?",
    "Night owl mode, {name}",
    "Belum tidur, {name}?",
    "Begadang lagi, {name}?",
    "Wis bengi, {name}. Durung turu?",
    "Buenas noches, {name}. Or is it already buenos dias?",
    "Welcome to the insomnia club, {name}",
    "The quiet hours suit you, {name}",
    "Sleep is a feature too, {name}",
    "Midnight build, {name}?",
    "Moonlight shift, {name}",
  ],
  MORNING: [
    "Good morning, {name}",
    "Rise and shine, {name}",
    "Early bird, {name}?",
    "Selamat pagi, {name}",
    "Ohayo, {name}",
    "Buongiorno, {name}",
    "Guten Morgen, {name}",
    "Bonjour, {name}",
    "Sugeng enjang, {name}",
    "Coffee first, maps second, {name}",
    "A fresh day, a fresh build, {name}",
    "Pagi, {name}. Kopinya sudah?",
    "Top of the morning, {name}",
    "New day, new frames, {name}",
    "Morning, {name}. Ready to map?",
    "Bom dia, {name}",
  ],
  AFTERNOON: [
    "Good afternoon, {name}",
    "Selamat siang, {name}",
    "Lunch break yet, {name}?",
    "Sudah makan siang, {name}?",
    "Buenas tardes, {name}",
    "Konnichiwa, {name}",
    "Bon apres-midi, {name}",
    "Halfway through the day, {name}",
    "Sugeng siang, {name}",
    "Post-lunch focus, {name}?",
    "Ciao, {name}",
    "Midday check-in, {name}",
  ],
  EVENING: [
    "Good evening, {name}",
    "Selamat sore, {name}",
    "Golden hour, {name}",
    "Sore-sore begini enaknya ngopi, {name}",
    "Buona sera, {name}",
    "Guten Tag, {name}",
    "Home stretch, {name}",
    "Winding down, {name}?",
    "Sugeng sonten, {name}",
    "Almost time to wrap up, {name}",
    "How did the day go, {name}?",
    "Afternoon slump survivor, {name}",
  ],
  NIGHT: [
    "Good evening, {name}",
    "Selamat malam, {name}",
    "Buenas noches, {name}",
    "Konbanwa, {name}",
    "Bonsoir, {name}",
    "Guten Abend, {name}",
    "Sugeng dalu, {name}",
    "Night shift, {name}?",
    "Burning the midnight oil, {name}?",
    "Lembur, {name}?",
    "Still at it, {name}?",
    "Cozy night for mapping, {name}",
    "The city sleeps, the dashboard doesn't, {name}",
    "Malam, {name}. Semangat ya!",
  ],
  WEEKDAY: {
    0: ["Sunday mode, {name}", "Even Sundays have builds, {name}"],
    1: ["Monday again, {name}", "Fresh week, fresh maps, {name}"],
    3: ["Midweek, {name}. Keep going"],
    4: ["Almost Friday, {name}"],
    5: ["It's Friday, {name}", "Friday build, {name}?"],
    6: ["Weekend session, {name}?", "Working on a Saturday, {name}?"],
  } as Record<number, readonly string[]>,
} as const;

export type HourBucket = "LATE" | "MORNING" | "AFTERNOON" | "EVENING" | "NIGHT";

export function getHourBucket(hour: number): HourBucket {
  if (hour >= 0 && hour <= 4) return "LATE";
  if (hour >= 5 && hour <= 11) return "MORNING";
  if (hour >= 12 && hour <= 14) return "AFTERNOON";
  if (hour >= 15 && hour <= 18) return "EVENING";
  return "NIGHT";
}

export function formatGreeting(template: string, name?: string): string {
  const trimmed = name ? name.trim() : "";
  if (!trimmed) {
    return template
      .replace(/,\s*\{name\}/g, "")
      .replace(/\{name\},\s*/g, "")
      .replace(/\{name\}/g, "")
      .trim();
  }
  return template.replace(/\{name\}/g, trimmed);
}

export function extractNameFromEmail(email: string | null | undefined): string {
  if (!email) return "";
  const beforeAt = email.split("@")[0] || "";
  // cut at the first ".", "_", "-", "+", or digit
  const match = beforeAt.match(/^([a-zA-Z]+)/);
  if (!match || !match[1]) return "";
  const raw = match[1];
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

export function greetingFor(
  hour: number,
  name: string,
  opts?: { weekday?: number; rand?: () => number }
): string {
  const rng = opts?.rand ?? Math.random;
  const weekday = opts?.weekday;
  const extras = weekday !== undefined ? GREETINGS.WEEKDAY[weekday] : undefined;

  if (extras && extras.length > 0) {
    const r = rng();
    if (r < 0.25) {
      const extraIndex = Math.min(
        extras.length - 1,
        Math.max(0, Math.floor(rng() * extras.length))
      );
      return formatGreeting(extras[extraIndex], name);
    }
  }

  const bucket = getHourBucket(hour);
  const pool = GREETINGS[bucket];
  const r = rng();
  const index = Math.min(pool.length - 1, Math.max(0, Math.floor(r * pool.length)));
  return formatGreeting(pool[index], name);
}
