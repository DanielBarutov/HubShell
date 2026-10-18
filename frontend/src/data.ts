import type { Booking, Client, Workstation } from "./types";

export const workstations: Workstation[] = [
  { id: "hall-01", name: "Avalonia Linux smoke", group: "Обычный зал", status: "busy", client: "DanielBarutov", session: "05 мин", tariff: "Поминутно" },
  { id: "hall-02", name: "PC5", group: "Обычный зал", status: "offline" },
  { id: "vip-01", name: "VIP-01", group: "VIP-зона", status: "busy", client: "m0onlight", session: "01:42:16" },
  { id: "vip-02", name: "VIP-02", group: "VIP-зона", status: "online" },
  { id: "vip-03", name: "VIP-03", group: "VIP-зона", status: "busy", client: "w1ldcard", session: "00:38:44" },
  { id: "vip-04", name: "VIP-04", group: "VIP-зона", status: "maintenance", lastSeen: "сегодня, 09:42" },
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
  { id: "c-04", nickname: "DanielBarutov", phone: "+7 951 159-24-29", balance: 378, bonus: 1240, category: "VIP" },
  { id: "c-05", nickname: "LiveSale1787945715", phone: "+7 999 472-86-60", balance: 4.5, bonus: 120, category: "Без категории" },
  { id: "c-06", nickname: "SmokeClient192557", phone: "+7 901 222-10-11", balance: 7.5, bonus: 85, category: "Без категории" },
  { id: "c-07", nickname: "V2 deposit smoke 3071ddd6", phone: "+7 999 472-92-04", balance: 5, bonus: 40, category: "Без категории" },
  { id: "c-08", nickname: "avalonia_3b06681e73", phone: "+7 999 472-86-60", balance: 0, bonus: 320, category: "Постоянный" },
  { id: "c-11", nickname: "avalonia_9dc1516fa7", phone: "+7 999 335-43-10", balance: 0, bonus: 75, category: "Без категории" },
  { id: "c-12", nickname: "live-v2-accepted-c0a8b4e2", phone: "+7 999 472-92-04", balance: 0, bonus: 60, category: "Без категории" },
  { id: "c-09", nickname: "persist-key-5006dfdf", phone: "+7 999 717-92-93", balance: 0, bonus: 30, category: "Гость" },
  { id: "c-13", nickname: "persist-key-a5c0a026", phone: "+7 999 412-41-40", balance: 0, bonus: 25, category: "Без категории" },
  { id: "c-10", nickname: "test", phone: "+7 000 000-00-00", balance: 0, bonus: 0, category: "Без категории" },
];
