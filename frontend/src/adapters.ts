import type { BackendClient, BackendSession, BackendWorkstation } from "./api";
import type { Client, Workstation } from "./types";

export function toUiWorkstation(
  workstation: BackendWorkstation,
  activeSession?: BackendSession,
  groupName?: string,
  clientName?: string,
  tariffName?: string,
): Workstation {
  const technicalStatus = {
    online: "online",
    stale: "stale",
    offline: "offline",
    disabled: "maintenance",
    unknown: "offline",
  }[workstation.status] as Workstation["status"];
  const sessionAge = activeSession
    ? `${Math.max(0, Math.floor((Date.now() - Date.parse(activeSession.started_at)) / 60_000))} мин`
    : undefined;

  return {
    id: workstation.id,
    name: workstation.name,
    group: groupName ?? (workstation.group_id?.toLowerCase().includes("vip") ? "VIP-зона" : "Обычный зал"),
    status: activeSession ? "busy" : technicalStatus,
    client: activeSession?.guest_name ?? clientName ?? (activeSession?.client_id ? "Клиент" : undefined),
    tariff: tariffName ?? activeSession?.tariff_id ?? undefined,
    session: sessionAge,
    sessionId: activeSession?.id,
    lastSeen: workstation.last_seen_at ?? undefined,
    position: workstation.position,
    groupId: workstation.group_id,
    deviceId: workstation.device_id,
    macAddress: workstation.mac_address,
    installationBound: workstation.installation_bound,
  };
}

export function toUiClient(client: BackendClient): Client {
  return {
    id: client.id,
    nickname: client.nickname,
    phone: client.phone ?? "—",
    balance: client.balance_cents / 100,
    bonus: client.balance_bonus,
    category: client.discount_category ?? "Без категории",
  };
}
