/**
 * Pure functions for greeting generation based on local hour and user name.
 */

export function extractNameFromEmail(email: string | null | undefined): string {
  if (!email) return "";
  const beforeAt = email.split("@")[0] || "";
  // cut at the first ".", "_", "-", "+", or digit
  const match = beforeAt.match(/^([a-zA-Z]+)/);
  if (!match || !match[1]) return "";
  const raw = match[1];
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

export function greetingFor(hour: number, name: string): string {
  const trimmed = name.trim();
  if (hour >= 5 && hour <= 11) {
    return trimmed ? `Good morning, ${trimmed}` : "Good morning";
  }
  if (hour >= 12 && hour <= 14) {
    return trimmed ? `Good afternoon, ${trimmed}` : "Good afternoon";
  }
  if (hour >= 15 && hour <= 18) {
    return trimmed ? `Good evening, ${trimmed}` : "Good evening";
  }
  if (hour >= 19 && hour <= 23) {
    return trimmed ? `Good night, ${trimmed}` : "Good night";
  }
  // hour 0..4
  return trimmed ? `You still awake, ${trimmed}??` : "You still awake??";
}
