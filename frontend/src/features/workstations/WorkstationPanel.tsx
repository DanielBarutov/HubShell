import { useState } from "react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendWorkstationGroup } from "../../api";
import { X } from "lucide-react";
import type { Workstation } from "../../types";

export function WorkstationPanel({
  api,
  workstation,
  groups,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  workstation?: Workstation;
  groups: BackendWorkstationGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [equipmentType, setEquipmentType] = useState<"pc" | "xbox">(workstation?.equipmentType ?? "pc");
  const [deviceId] = useState(workstation?.deviceId ?? "");
  const [macAddress, setMacAddress] = useState(workstation?.macAddress ?? "");
  const [name, setName] = useState(workstation?.name ?? "");
  const [groupId, setGroupId] = useState(
    workstation?.groupId ??
      (workstation?.group === "VIP-зона" ? "vip" : "main"),
  );
  const [position, setPosition] = useState(
    workstation?.position && workstation.position > 0
      ? String(workstation.position)
      : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [relayEnabled, setRelayEnabled] = useState(Boolean(workstation?.relaySettings));
  const [relayIp, setRelayIp] = useState(workstation?.relaySettings?.ip ?? "");
  const [relayPort, setRelayPort] = useState(String(workstation?.relaySettings?.port ?? 8081));
  const [relayDeviceid, setRelayDeviceid] = useState(workstation?.relaySettings?.deviceid ?? "");
  const [relayTesting, setRelayTesting] = useState(false);
  const [relayResult, setRelayResult] = useState<string | null>(null);
  const relaySettings = equipmentType === "xbox" && relayEnabled
    ? {ip: relayIp.trim(), port: Number(relayPort), deviceid: relayDeviceid.trim()}
    : null;
  const relaySaved = relayEnabled && Boolean(workstation?.relaySettings)
    && relaySettings?.ip === workstation?.relaySettings?.ip
    && relaySettings?.port === workstation?.relaySettings?.port
    && relaySettings?.deviceid === workstation?.relaySettings?.deviceid;

  const testRelay = async (state: "on" | "off") => {
    if (!workstation || !relaySaved) return;
    setRelayTesting(true);
    setRelayResult(null);
    setError(null);
    try {
      const result = await api.testWorkstationRelay(workstation.id, state);
      setRelayResult(result.state === "on" ? "Реле включено; состояние подтверждено" : "Реле выключено; состояние подтверждено");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось проверить реле");
    } finally {
      setRelayTesting(false);
    }
  };

  const availableGroups = groups.length
    ? groups.some((item) => item.id === groupId) || !workstation
      ? groups
      : [
          {
            id: groupId,
            name: workstation.group,
            theme: "standard" as const,
            updated_at: null,
          },
          ...groups,
        ]
    : [];

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedPosition = position.trim() ? Number(position) : null;
    if (
      (!workstation && equipmentType === "pc" && !macAddress.trim()) ||
      !name.trim() ||
      (parsedPosition !== null &&
        (!Number.isInteger(parsedPosition) || parsedPosition < 1))
    ) {
      setError(
        workstation
          ? "Укажите название и корректную позицию"
          : equipmentType === "xbox" ? "Укажите название и корректную позицию" : "Укажите MAC-адрес, название и корректную позицию",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (workstation) {
        await api.updateWorkstation(workstation.id, {
          name: name.trim(),
          mac_address: macAddress.trim() || null,
          group_id: groupId || null,
          position: parsedPosition,
          ...(equipmentType === "xbox" ? {relay_settings: relaySettings} : {}),
        });
      } else {
        await api.registerWorkstation({
          device_id: deviceId.trim() || undefined,
          equipment_type: equipmentType,
          relay_settings: relaySettings,
          mac_address: equipmentType === "pc" ? macAddress.trim() : undefined,
          name: name.trim(),
          group_id: groupId || null,
          position: parsedPosition,
          capabilities: equipmentType === "xbox" ? [] : [
            "display-lock.v2",
            "v2.local-ledger",
            "v2.device-commands",
            "widget.v2",
          ],
        });
      }
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось добавить игровое место",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3 border-b border-primary/15! pb-4">
        <div>
          <p className="text-xs text-base-content/60!">Оборудование</p>
          <h2 className="mt-1 text-xl font-bold">
            {workstation
              ? "Редактировать игровое место"
              : "Новое игровое место"}
          </h2>
        </div>
        <button
          className="btn btn-ghost btn-circle btn-sm"
          aria-label="Закрыть панель"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>
      <form className="flex flex-col gap-3" onSubmit={submit}>
        {!workstation && <label className="flex flex-col gap-1 text-sm">
          Тип места
          <select className="select select-sm" value={equipmentType} onChange={(event) => setEquipmentType(event.target.value as "pc" | "xbox")}>
            <option value="pc">ПК</option><option value="xbox">Xbox</option>
          </select>
        </label>}
        {!workstation && equipmentType === "pc" && (
          <label className="flex flex-col gap-1 text-sm">
            MAC-адрес игрового ПК
            <input
              className="input input-sm"
              value={macAddress}
              onChange={(event) => setMacAddress(event.target.value)}
              placeholder="AA:BB:CC:DD:EE:FF"
              autoFocus
            />
          </label>
        )}
        {workstation && equipmentType === "pc" && (
          <>
            <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
              <span className="text-base-content/60!">MAC-адрес</span>
              <strong>{macAddress || "Не назначен"}</strong>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              MAC-адрес игрового ПК
              <input
                className="input input-sm"
                value={macAddress}
                onChange={(event) => setMacAddress(event.target.value)}
                placeholder="AA:BB:CC:DD:EE:FF"
              />
            </label>
            <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
              <span className="text-base-content/60!">Состояние привязки</span>
              <strong>
                {workstation.installationBound
                  ? "Клиент привязан"
                  : "Ожидает запуска клиента"}
              </strong>
            </div>
            {workstation.installationBound && (
              <p className="mt-1 text-sm text-base-content/70!">
                Это место уже связано с установкой. Смена MAC доступна через
                отдельную операцию перепривязки, чтобы не потерять защиту
                устройства.
              </p>
            )}
          </>
        )}
        {workstation && equipmentType === "pc" && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
            <span className="text-base-content/60!">Device ID</span>
            <strong>{deviceId}</strong>
          </div>
        )}
        <label className="flex flex-col gap-1 text-sm">
          Название
          <input
            className="input input-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="VIP-01"
            autoFocus={Boolean(workstation)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Зона
          <select
            className="select select-sm"
            value={groupId}
            onChange={(event) => setGroupId(event.target.value)}
          >
            {availableGroups.length ? (
              availableGroups.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))
            ) : (
              <>
                <option value="main">Обычный зал</option>
                <option value="vip">VIP-зона</option>
              </>
            )}
          </select>
        </label>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
          <span className="text-base-content/60!">Расчёт времени</span>
          <strong>Время и стоимость считаются автоматически</strong>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          Позиция на карте
          <input
            className="input input-sm"
            type="number"
            min="1"
            step="1"
            value={position}
            onChange={(event) => setPosition(event.target.value)}
            placeholder="Не задана"
          />
        </label>
        {error && (
          <div
            className="rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        {equipmentType === "xbox" && <fieldset className="fieldset rounded-box border border-base-300 p-3" disabled={submitting || relayTesting}>
          <legend className="fieldset-legend">Реле DIY</legend>
          <label className="label justify-start gap-2">
            <input className="checkbox checkbox-sm" type="checkbox" checked={relayEnabled} onChange={(event) => {setRelayEnabled(event.target.checked); setRelayResult(null);}} />
            Настроить реле
          </label>
          {relayEnabled && <>
            <label className="flex flex-col gap-1 text-sm">IP реле
              <input className="input input-sm w-full" value={relayIp} maxLength={45} onChange={(event) => {setRelayIp(event.target.value); setRelayResult(null);}} placeholder="192.168.1.100" required />
            </label>
            <label className="flex flex-col gap-1 text-sm">Порт реле
              <input className="input input-sm w-full" type="number" value={relayPort} onChange={(event) => {setRelayPort(event.target.value); setRelayResult(null);}} min={1} max={65535} step={1} required />
            </label>
            <label className="flex flex-col gap-1 text-sm">deviceid реле
              <input className="input input-sm w-full" value={relayDeviceid} maxLength={128} onChange={(event) => {setRelayDeviceid(event.target.value); setRelayResult(null);}} required />
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-sm" disabled={!relaySaved} onClick={() => void testRelay("on")}>Тест: включить</button>
              <button type="button" className="btn btn-sm" disabled={!relaySaved} onClick={() => void testRelay("off")}>Тест: выключить</button>
            </div>
            {!relaySaved && <p className="text-sm text-base-content/70">Сохраните настройки перед тестом.</p>}
            {relayTesting && <p role="status">Проверяем состояние реле…</p>}
            {relayResult && <p className="text-sm text-success" role="status">{relayResult}</p>}
          </>}
        </fieldset>}
        <button
          className="btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting || relayTesting}
        >
          {submitting
            ? "Сохраняем..."
            : workstation
              ? "Сохранить изменения"
              : "Добавить место"}
        </button>
        {equipmentType === "pc" && <p className="mt-1 text-sm text-base-content/70!">
          После запуска EXE клиент сам найдёт это место по MAC и получит
          настройки группы.
        </p>}
      </form>
    </div>
  );
}
