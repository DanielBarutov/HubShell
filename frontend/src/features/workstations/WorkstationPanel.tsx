import { useState } from "react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendWorkstationGroup } from "../../api";
import { X } from "lucide-react";
import type { Workstation } from "../../types";

export function WorkstationPanel({ api, workstation, groups, onClose, onSaved }: { api: GameClubApi; workstation?: Workstation; groups: BackendWorkstationGroup[]; onClose: () => void; onSaved: () => void }) {
  const [deviceId] = useState(workstation?.deviceId ?? "");
  const [macAddress, setMacAddress] = useState(workstation?.macAddress ?? "");
  const [name, setName] = useState(workstation?.name ?? "");
  const [groupId, setGroupId] = useState(workstation?.groupId ?? (workstation?.group === "VIP-зона" ? "vip" : "main"));
  const [position, setPosition] = useState(workstation?.position && workstation.position > 0 ? String(workstation.position) : "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const availableGroups = groups.length
    ? groups.some((item) => item.id === groupId) || !workstation
      ? groups
      : [{ id: groupId, name: workstation.group, theme: "standard" as const, updated_at: null }, ...groups]
    : [];

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedPosition = position.trim() ? Number(position) : null;
    if ((!workstation && !macAddress.trim()) || !name.trim() || (parsedPosition !== null && (!Number.isInteger(parsedPosition) || parsedPosition < 1))) {
      setError(workstation ? "Укажите название и корректную позицию" : "Укажите MAC-адрес, название и корректную позицию");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (workstation) {
        await api.updateWorkstation(workstation.id, { name: name.trim(), mac_address: macAddress.trim() || null, group_id: groupId || null, position: parsedPosition });
      } else {
        await api.registerWorkstation({
          device_id: deviceId.trim() || undefined,
          mac_address: macAddress.trim(),
          name: name.trim(),
          group_id: groupId || null,
          position: parsedPosition,
          capabilities: ["commands.v1", "theme.v1", "sessions.v1"],
        });
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось добавить игровое место");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><div className="panel-header"><div><p>Оборудование</p><h2>{workstation ? "Редактировать игровое место" : "Новое игровое место"}</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}>{!workstation && <label>MAC-адрес игрового ПК<input value={macAddress} onChange={(event) => setMacAddress(event.target.value)} placeholder="AA:BB:CC:DD:EE:FF" autoFocus /></label>}{workstation && <><div className="detail-row"><span>MAC-адрес</span><strong>{macAddress || "Не назначен"}</strong></div><label>MAC-адрес игрового ПК<input value={macAddress} onChange={(event) => setMacAddress(event.target.value)} placeholder="AA:BB:CC:DD:EE:FF" /></label><div className="detail-row"><span>Состояние привязки</span><strong>{workstation.installationBound ? "Клиент привязан" : "Ожидает запуска клиента"}</strong></div>{workstation.installationBound && <p className="subheading">Это место уже связано с установкой. Смена MAC доступна через отдельную операцию перепривязки, чтобы не потерять защиту устройства.</p>}</>}{workstation && <div className="detail-row"><span>Device ID</span><strong>{deviceId}</strong></div>}<label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="VIP-01" autoFocus={Boolean(workstation)} /></label><label>Зона<select value={groupId} onChange={(event) => setGroupId(event.target.value)}>{availableGroups.length ? availableGroups.map((item) => <option value={item.id} key={item.id}>{item.name}</option>) : <><option value="main">Обычный зал</option><option value="vip">VIP-зона</option></>}</select></label><label>Позиция на карте<input type="number" min="1" step="1" value={position} onChange={(event) => setPosition(event.target.value)} placeholder="Не задана" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : workstation ? "Сохранить изменения" : "Добавить место"}</button><p className="subheading">После запуска EXE клиент сам найдёт это место по MAC и получит настройки группы.</p></form></div>;
}
