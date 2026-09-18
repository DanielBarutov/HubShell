import { useEffect, useState } from "react";
import { ChevronRight, Computer, Receipt, ShoppingCart, Settings, WalletCards } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendSessionMeter, BackendSessionSnapshot, BackendTariff, BackendTransferOffer } from "../../api";
import { toUiClient } from "../../adapters";
import { getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { statusMeta } from "../../shared/constants";
import type { Client, Workstation } from "../../types";

export function PcPanel({
  pc,
  workstations,
  tariffs,
  onClose,
  onEdit,
  onBook,
  onDeposit,
  onOpenSale,
  onSessionChanged,
  client,
  api,
}: {
  pc: Workstation;
  workstations: Workstation[];
  tariffs: BackendTariff[];
  onClose: () => void;
  onEdit: () => void;
  onBook: () => void;
  onDeposit: (client?: Client, bonusOnly?: boolean) => void;
  onOpenSale: () => void;
  onSessionChanged: () => void;
  client?: Client;
  api?: GameClubApi;
}) {
  const meta = statusMeta[pc.status];
  const [operationState, setOperationState] = useState<string | null>(null);
  const [operationSuccess, setOperationSuccess] = useState(false);
  const [clientQuery] = useState("");
  const [clientCandidate, setClientCandidate] = useState<Client | undefined>();
  const [tariffId, setTariffId] = useState<string>("");
  const [tariffQuantity] = useState("1");
  const [meter, setMeter] = useState<BackendSessionMeter | null>(null);
  const [sessionSnapshot, setSessionSnapshot] = useState<BackendSessionSnapshot | null>(null);
  const [stoppedSessionId, setStoppedSessionId] = useState<string | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const [transferTargetId, setTransferTargetId] = useState("");
  const [transferOffer, setTransferOffer] = useState<BackendTransferOffer | null>(null);
  const clientField = getSearchField(clientQuery);

  useEffect(() => {
    const workstationGroupId = pc.groupId?.trim().toLowerCase();
    const availableTariffs = tariffs.filter((item) => Boolean(workstationGroupId) && item.lifecycle === "published" && item.active && item.billing_mode === "block" && (item.sale_channel ?? "both") !== "self_service" && (item.group_id === null || item.group_id.trim().toLowerCase() === workstationGroupId));
    setTariffId((current) => availableTariffs.some((item) => item.id === current) ? current : availableTariffs[0]?.id || "");
  }, [pc.groupId, tariffs]);

  useEffect(() => {
    if (!api || pc.status !== "busy" || !pc.sessionId) {
      setMeter(null);
      setSessionSnapshot(null);
      return undefined;
    }
    let active = true;
    const refreshSnapshot = () => {
      void api.getSessionSnapshot(pc.sessionId!).then((value) => {
        if (active) {
          setSessionSnapshot(value);
          setMeter(value.meter);
        }
      }).catch(() => {
        if (active) {
          setSessionSnapshot(null);
          setMeter(null);
        }
      });
    };
    refreshSnapshot();
    const timer = window.setInterval(refreshSnapshot, 10_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, pc.sessionId, pc.status]);

  useEffect(() => {
    if (!api || !clientField) {
      setClientCandidate(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(clientQuery, clientField);
        if (active) {
          setClientCandidate(found[0] ? toUiClient(found[0]) : undefined);
        }
      } catch {
        if (active) {
          setClientCandidate(undefined);
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientField, clientQuery, pc.status]);

  const startOrStop = async () => {
    if (!api) {
      setOperationSuccess(false);
      setOperationState("Mock-режим: сессия не отправлялась");
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      if (pc.status === "busy") {
        if (!pc.sessionId) {
          setOperationState("Не найден ID активной сессии");
          return;
        }
        if (!window.confirm(`Прервать сессию на «${pc.name}»? Время будет рассчитано по фактическому окончанию.`)) {
          return;
        }
        const session = await api.interruptSession(
          pc.sessionId,
          "Клиент завершил сессию раньше",
          crypto.randomUUID(),
        );
        setStoppedSessionId(session.id);
        setOperationSuccess(true);
        setOperationState("Сессия прервана. Проверьте итог и выполните списание.");
      } else {
        const entry = await api.checkEntry(pc.id, clientCandidate?.id);
        if (!entry.allowed) {
          setOperationState(`Вход запрещён: ${entry.reason}`);
          return;
        }
        await api.startSession(
          {
            workstation_id: pc.id,
            client_id: clientCandidate?.id,
            guest_name: clientCandidate ? undefined : "Гость",
            source: "operator",
            tariff_id: tariffId || undefined,
            tariff_quantity: Math.max(1, Math.min(100, Number(tariffQuantity) || 1)),
          },
          crypto.randomUUID(),
        );
        setOperationSuccess(true);
        setOperationState("Сессия открыта");
      }
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось изменить сессию");
    } finally {
      setSubmitting(false);
    }
  };

  const activatePackage = async (entitlementId: string) => {
    if (!api || !sessionSnapshot?.client_id) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      await api.activateEntitlement(sessionSnapshot.client_id, entitlementId);
      const refreshed = await api.getSessionSnapshot(sessionSnapshot.session.id);
      setSessionSnapshot(refreshed);
      setMeter(refreshed.meter);
      setOperationSuccess(true);
      setOperationState("Пакет активирован на сервере");
    } catch (error) {
      setOperationState(error instanceof ApiError ? error.message : "Не удалось активировать пакет");
    } finally {
      setSubmitting(false);
    }
  };
  const charge = async () => {
    if (!api || !stoppedSessionId) {
      return;
    }
    if (!window.confirm("Списать стоимость завершённой сессии по действующему тарифу?")) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      const result = await api.chargeSession(stoppedSessionId, crypto.randomUUID());
      setOperationSuccess(true);
      setOperationState(
        `Списано ${(result.amount_cents / 100).toLocaleString("ru-RU")} ₽. Баланс: ${(result.client_balance_cents / 100).toLocaleString("ru-RU")} ₽`,
      );
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось списать с баланса");
    } finally {
      setSubmitting(false);
    }
  };

  const transferSession = async () => {
    if (!api || !pc.sessionId || !transferTargetId) {
      setOperationState("Выберите свободное место для переноса");
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      const offer = await api.createTransferOffer(
        pc.sessionId,
        transferTargetId,
        `transfer-offer-${crypto.randomUUID()}`,
      );
      setTransferOffer(offer);
      const confirmation = offer.warning
        ? `${offer.warning}\n\nПодтвердить перенос?`
        : "Подтвердить перенос активной сессии на выбранный ПК?";
      if (!window.confirm(confirmation)) {
        setOperationState("Перенос не подтверждён");
        return;
      }
      const result = await api.confirmTransfer(
        offer.id,
        `transfer-confirm-${crypto.randomUUID()}`,
      );
      setOperationSuccess(true);
      setOperationState(`Сессия перенесена на ${workstations.find((item) => item.id === result.workstation_id)?.name ?? "новое место"}`);
      onSessionChanged();
    } catch (error) {
      setOperationState(error instanceof ApiError ? error.message : "Не удалось перенести сессию");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleAvailability = async () => {
    if (!api || !window.confirm(`${pc.status === "maintenance" ? "Включить" : "Отключить"} игровое место «${pc.name}»?`)) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      if (pc.status === "maintenance") {
        await api.enableWorkstation(pc.id);
        setOperationState("Место включено; ждём подключения клиента");
      } else {
        await api.disableWorkstation(pc.id, "Отключено оператором из панели");
        setOperationState("Место отключено; новые команды заблокированы");
      }
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось отключить место");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner">
    <PanelHeader title={pc.name} subtitle={pc.group} onClose={onClose} />
    <div className="panel-pc-hero">
      <div className={"large-pc-icon " + pc.status}><Computer size={50} strokeWidth={1.2} /></div>
      <div><span className={"pill-status " + meta.className}><i /> {meta.label}</span><h2>{pc.client || "Место свободно"}</h2><p>{pc.session ? "Сессия началась " + pc.session + " назад" : pc.status === "offline" ? "Нет связи; новые операции заблокированы" : pc.lastSeen || "Готово к новой сессии"}</p>{meter && <small className="meter-status">{meter.package_minutes > 0 ? `Пакет · использовано ${meter.package_minutes} мин` : "Поминутно"} · списано ${(meter.billed_cents / 100).toLocaleString("ru-RU")} ₽ · {meter.billed_minutes} мин · {meter.status === "exhausted" ? "баланс исчерпан" : "активно"}</small>}</div>
    </div>
    <div className="panel-section">
      <div className="detail-row"><span>Группа</span><strong>{pc.group}</strong></div>
      <div className="detail-row"><span>Позиция на карте</span><strong>{pc.position ?? "—"}</strong></div>
      <div className="detail-row"><span>Устройство</span><strong>{pc.name}</strong></div>
      {sessionSnapshot?.active_entitlement && <div className="detail-row"><span>Активный пакет</span><strong>{sessionSnapshot.active_entitlement.remaining_minutes} мин осталось</strong></div>}
    </div>
    {sessionSnapshot && sessionSnapshot.entitlements.some((item) => item.status === "queued") && <div className="panel-section"><div className="card-heading"><div><h3>Очередь пакетов</h3><p>Следующие пакеты активируются по порядку</p></div></div>{sessionSnapshot.entitlements.filter((item) => item.status === "queued").map((item) => <div className="detail-row" key={item.id}><span>#{item.queue_position} · {item.remaining_minutes} мин</span><button className="text-button" onClick={() => void activatePackage(item.id)} disabled={submitting || Boolean(sessionSnapshot.active_entitlement)}>Активировать</button></div>)}</div>}
    {(pc.status === "online" || pc.status === "busy") && <button type="button" className="sale-entry-card" onClick={onOpenSale}>
      <div className="sale-entry-icon"><Receipt size={20} /></div>
      <div><strong>Оформить продажу</strong><span>Время, товары и покупатель — в одном окне</span></div>
      <ChevronRight size={17} />
    </button>}
    <div className="panel-actions">
      {pc.status === "busy" && client && <button className="secondary-button wide" onClick={() => onDeposit(client)}><WalletCards size={15} /> Пополнить депозит</button>}
      <button className="secondary-button wide" onClick={onEdit}><Settings size={15} /> Редактировать ПК</button>
      {pc.status === "busy" ? <><button className="primary-button wide" onClick={() => void startOrStop()} disabled={submitting || Boolean(stoppedSessionId)}>{submitting ? "Сохраняем..." : "Прервать сессию"}</button><button className="secondary-button wide" onClick={onOpenSale} disabled={submitting}><ShoppingCart size={15} /> Продать товар</button></> : <button className="primary-button wide" onClick={onOpenSale} disabled={pc.status !== "online"}><ShoppingCart size={15} /> Открыть продажи</button>}
      {stoppedSessionId && api && <button className="primary-button wide" onClick={() => void charge()} disabled={submitting}>Списать по тарифу</button>}
      {pc.status === "busy" && api && <>
        <label>Перенести на место<select value={transferTargetId} onChange={(event) => setTransferTargetId(event.target.value)} disabled={submitting}>
          <option value="">Выберите свободный ПК</option>
          {workstations.filter((item) => item.id !== pc.id && item.status === "online").map((item) => <option value={item.id} key={item.id}>{item.name} · {item.group}</option>)}
        </select></label>
        <button className="secondary-button wide" onClick={() => void transferSession()} disabled={submitting || !transferTargetId}>Перенести сессию</button>
        {transferOffer && <small className="muted">Перенос создан · действует до {new Date(transferOffer.expires_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>}
      </>}
      <button className="secondary-button wide" onClick={onBook} disabled={pc.status !== "online"}>Забронировать место</button>
      {operationState && <div className={`${operationSuccess ? "form-success" : "form-error"} command-result`} role={operationSuccess ? "status" : "alert"} aria-live="polite">{operationState}</div>}
    </div>
    <button className="danger-button" onClick={() => void toggleAvailability()} disabled={!api || submitting} aria-disabled={!api}>{pc.status === "maintenance" ? "Включить место" : "Отключить место"} <ChevronRight size={15} /></button>
    <button className="danger-button" onClick={async () => { if (!api || !window.confirm("Удалить «" + pc.name + "» из активной карты?")) return; setSubmitting(true); try { await api.deleteWorkstation(pc.id); onSessionChanged(); onClose(); } catch (error) { setOperationSuccess(false); setOperationState(error instanceof ApiError ? error.message : "Не удалось удалить место"); } finally { setSubmitting(false); } }}>Удалить из карты</button>
  </div>;
}
