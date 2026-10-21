export function generateUUID() {
  // Если randomUUID доступен (HTTPS/localhost) — используем его
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Иначе — генерируем вручную через getRandomValues
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  // Версия 4 (биты 12-15 в 7-м байте = 0100)
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  // Вариант RFC 4122 (биты 6-7 в 9-м байте = 10)
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0'));

  return (
    hex.slice(0, 4).join('') +
    '-' +
    hex.slice(4, 6).join('') +
    '-' +
    hex.slice(6, 8).join('') +
    '-' +
    hex.slice(8, 10).join('') +
    '-' +
    hex.slice(10, 16).join('')
  );
}
