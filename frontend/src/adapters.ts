import type { BackendClient, BackendSession, BackendWorkstation } from "./api";
import type { Client, Workstation } from "./types";

export function toUiWorkstation(
  workstation: BackendWorkstation,
  groupName?: string,
  clientName?: string,
  tariffName?: string,
): Workstation {
  const activeSession: BackendSession | undefined = workstation.session_snapshot?.session;
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
  const effectiveGroupId = workstation.group_id?.trim()
    || (groupName?.toLowerCase().includes("vip") ? "vip" : "main");

  return {
    id: workstation.id,
    name: workstation.name,
    equipmentType: workstation.equipment_type ?? "pc",
    relaySettings: workstation.relay_settings ?? null,
    group: groupName ?? (effectiveGroupId === "vip" ? "VIP-зона" : "Обычный зал"),
    status: activeSession ? "busy" : technicalStatus,
    client: activeSession?.guest_name ?? clientName ?? (activeSession?.client_id ? "Клиент" : undefined),
    clientId: activeSession?.client_id ?? undefined,
    tariff: tariffName ?? activeSession?.tariff_id ?? undefined,
    session: workstation.equipment_type === "xbox" && activeSession
      ? `Осталось ${workstation.session_snapshot?.active_tariff?.remaining_minutes ?? 0} мин`
      : sessionAge,
    sessionId: activeSession?.id,
    lastSeen: workstation.last_seen_at ?? undefined,
    position: workstation.position,
    groupId: effectiveGroupId,
    deviceId: workstation.device_id ?? undefined,
    macAddress: workstation.mac_address,
    installationBound: workstation.installation_bound,
    sessionSnapshot: workstation.session_snapshot ?? null,
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
    clientGroupId: client.client_group_id ?? null,
  };
}
