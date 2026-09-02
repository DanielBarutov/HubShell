export type PcStatus = "online" | "busy" | "stale" | "offline" | "maintenance";

export type Section = "dashboard" | "map" | "bookings" | "clients" | "catalog" | "analytics" | "cash" | "settings";

export type Workstation = {
  id: string;
  name: string;
  group: string;
  status: PcStatus;
  client?: string;
  tariff?: string;
  session?: string;
  sessionId?: string;
  lastSeen?: string;
  position?: number | null;
  groupId?: string | null;
  deviceId?: string;
  macAddress?: string | null;
  installationBound?: boolean;
};

export type Booking = {
  id: string;
  workstation: string;
  client: string;
  start: string;
  end: string;
  status: "Подтверждено" | "Активно" | "Ожидает";
};

export type Client = {
  id: string;
  nickname: string;
  phone: string;
  balance: number;
  bonus: number;
  category: string;
};
