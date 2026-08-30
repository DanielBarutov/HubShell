import type { Booking, Client, Workstation } from "./types";

export const workstations: Workstation[] = [
  { id: "vip-01", name: "VIP-01", group: "VIP-зона", status: "busy", client: "m0onlight", session: "01:42:16" },
  { id: "vip-02", name: "VIP-02", group: "VIP-зона", status: "online" },
  { id: "vip-03", name: "VIP-03", group: "VIP-зона", status: "busy", client: "w1ldcard", session: "00:38:44" },
  { id: "vip-04", name: "VIP-04", group: "VIP-зона", status: "maintenance", lastSeen: "сегодня, 09:42" },
  { id: "hall-01", name: "A-01", group: "Обычный зал", status: "online" },
  { id: "hall-02", name: "A-02", group: "Обычный зал", status: "busy", client: "n1ghtfox", session: "02:15:08" },
  { id: "hall-03", name: "A-03", group: "Обычный зал", status: "offline", lastSeen: "сегодня, 08:17" },
  { id: "hall-04", name: "A-04", group: "Обычный зал", status: "online" },
  { id: "hall-05", name: "A-05", group: "Обычный зал", status: "busy", client: "Kiborg", session: "00:12:31" },
  { id: "hall-06", name: "A-06", group: "Обычный зал", status: "online" },
  { id: "hall-07", name: "A-07", group: "Обычный зал", status: "offline", lastSeen: "вчера, 23:11" },
  { id: "hall-08", name: "A-08", group: "Обычный зал", status: "online" },
];

export const bookings: Booking[] = [
  { id: "b-01", workstation: "VIP-02", client: "s1lent", start: "12:00", end: "14:00", status: "Подтверждено" },
  { id: "b-02", workstation: "A-04", client: "night_walker", start: "13:30", end: "15:00", status: "Ожидает" },
  { id: "b-03", workstation: "A-06", client: "Dasha", start: "14:00", end: "17:00", status: "Подтверждено" },
  { id: "b-04", workstation: "VIP-01", client: "m0onlight", start: "10:00", end: "12:00", status: "Активно" },
];

export const clients: Client[] = [
  { id: "c-01", nickname: "NightFox", phone: "+7 999 123-45-67", balance: 1240, bonus: 120, category: "Постоянный" },
  { id: "c-02", nickname: "s1lent", phone: "+7 916 555-21-90", balance: 580, bonus: 40, category: "VIP" },
  { id: "c-03", nickname: "Kiborg", phone: "+7 901 222-10-10", balance: 320, bonus: 0, category: "Новый" },
];
