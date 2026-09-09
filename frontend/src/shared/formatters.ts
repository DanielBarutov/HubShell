export function getSearchField(value: string): "nickname" | "phone" | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const digits = normalized.replace(/\D/g, "");
  const phoneLike = /^[+\d\s()-]+$/.test(normalized);
  if (phoneLike) return digits.length >= 4 ? "phone" : null;
  return normalized.length >= 3 ? "nickname" : null;
}

export function formatRussianPhone(value: string): string {
  let digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.startsWith("8")) digits = `7${digits.slice(1)}`;
  if (digits.length === 10 && !digits.startsWith("7")) digits = `7${digits}`;
  if (digits.startsWith("7")) {
    const local = digits.slice(1);
    if (!local) return "+7";
    if (local.length <= 3) return `+7 (${local}`;
    if (local.length <= 6) return `+7 (${local.slice(0, 3)}) ${local.slice(3)}`;
    if (local.length <= 8) return `+7 (${local.slice(0, 3)}) ${local.slice(3, 6)}-${local.slice(6)}`;
    return `+7 (${local.slice(0, 3)}) ${local.slice(3, 6)}-${local.slice(6, 8)}-${local.slice(8)}`;
  }
  return digits ? `+${digits}` : "";
}

export function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localDateInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function cashMoney(cents: number): string {
  return `${(cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 })} ₽`;
}

export function cashIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
