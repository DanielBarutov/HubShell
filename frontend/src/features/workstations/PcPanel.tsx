import { useEffect, useState } from "react";
import {
  ChevronRight,
  Computer,
  Gamepad2,
  Receipt,
  Settings,
  WalletCards,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { statusMeta } from "../../shared/constants";
import type { Client, Workstation } from "../../types";
import type { DepositTarget } from "../workspace/uiSlice";

export function PcPanel({
  pc,
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
  onClose: () => void;
  onEdit: () => void;
  onBook: () => void;
  onDeposit: (
    client?: Client,
    bonusOnly?: boolean,
    target?: DepositTarget,
  ) => void;
  onOpenSale: () => void;
  onSessionChanged: () => void;
  client?: Client;
  api?: GameClubApi;
}) {
  const isXbox = pc.equipmentType === "xbox";
  const meta = statusMeta[pc.status];
  const [operationState, setOperationState] = useState<string | null>(null);
  const [operationSuccess, setOperationSuccess] = useState(false);
  // Во время активной сессии владелец не меняется. Запоздалый polling не должен
  // подменять доступные действия.
  const [sessionSnapshotState, setSessionSnapshotState] = useState(() => ({
    workstationId: pc.id,
    sessionId: pc.sessionId,
  }));
  const [submitting, setSubmitting] = useState(false);
  const hasActiveSession = pc.status === "busy";
  const snapshotChanged =
    sessionSnapshotState.workstationId !== pc.id ||
    sessionSnapshotState.sessionId !== pc.sessionId;
  const sessionSnapshot = pc.sessionSnapshot ?? null;

  useEffect(() => {
    if (!hasActiveSession || snapshotChanged) {
      setSessionSnapshotState({
        workstationId: pc.id,
        sessionId: pc.sessionId,
      });
    }
  }, [hasActiveSession, pc.id, pc.sessionId, snapshotChanged]);

  const dispatchDeviceCommand = async (
    commandType: "display.lock" | "system.restart",
  ) => {
    if (!api || pc.status === "maintenance" || pc.status === "offline") {
      return;
    }
    const confirmation =
      commandType === "system.restart"
        ? `Перезапустить «${pc.name}»? Клиент сначала будет заблокирован.`
        : `Заблокировать клиент на «${pc.name}»?`;
    if (!window.confirm(confirmation)) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      await api.dispatchDeviceCommand(pc.id, commandType, crypto.randomUUID());
      setOperationSuccess(true);
      setOperationState(
        commandType === "system.restart"
          ? "Команда перезапуска поставлена в очередь"
          : "Команда блокировки поставлена в очередь",
      );
    } catch (error) {
      setOperationState(
        error instanceof ApiError
          ? error.message
          : "Не удалось отправить команду",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const interruptSession = async () => {
    if (!api || !hasActiveSession || !pc.sessionId) {
      return;
    }
    if (
      !window.confirm(
        `Прервать сессию на «${pc.name}»? Весь неиспользованный остаток сгорит без возврата денег.`,
      )
    ) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      if (isXbox) await api.stopXboxSession(pc.sessionId);
      else await api.interruptSession(
        pc.sessionId,
        "Оператор прервал сессию из панели ПК",
        crypto.randomUUID(),
      );
      setOperationSuccess(true);
      setOperationState("Сессия завершена");
      onSessionChanged();
    } catch (error) {
      setOperationState(
        error instanceof ApiError
          ? error.message
          : "Не удалось прервать сессию",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const toggleAvailability = async () => {
    if (
      !api ||
      !window.confirm(
        `${pc.status === "maintenance" ? "Включить" : "Отключить"} игровое место «${pc.name}»?`,
      )
    ) {
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
      setOperationState(
        error instanceof ApiError
          ? error.message
          : "Не удалось отключить место",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const deleteWorkstation = async () => {
    if (!api || !window.confirm(`Удалить «${pc.name}» из активной карты?`)) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      await api.deleteWorkstation(pc.id);
      onSessionChanged();
      onClose();
    } catch (error) {
      setOperationState(
        error instanceof ApiError ? error.message : "Не удалось удалить место",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner pc-panel flex flex-col gap-4 p-5">
      <PanelHeader title={pc.name} subtitle={pc.group} onClose={onClose} />
      <div className="panel-pc-hero flex items-center gap-3 rounded-xl border border-primary/20! bg-base-200/70! p-4 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
        <div
          className={`large-pc-icon grid h-16 w-16 shrink-0 place-items-center rounded-xl bg-primary/15! text-primary! ${pc.status}`}
        >
          {isXbox ? <Gamepad2 size={50} strokeWidth={1.2} /> : <Computer size={50} strokeWidth={1.2} />}
        </div>
        <div className="min-w-0">
          <span className="pill-status badge badge-soft badge-success gap-1">
            <i className="h-1.5 w-1.5 rounded-full bg-current" /> {meta.label}
          </span>
          <h2 className="mt-2 text-lg font-bold">
            {pc.client || "Место свободно"}
          </h2>
          <p className="text-xs text-base-content/60!">
            {pc.session
              ? isXbox ? pc.session : `Сессия началась ${pc.session} назад`
              : pc.status === "offline"
                ? "Нет связи; новые операции заблокированы"
                : pc.lastSeen || "Готово к новой сессии"}
          </p>
          {sessionSnapshot?.meter && (
            <small className="meter-status mt-2 block text-xs text-primary!">
              {sessionSnapshot.meter.package_minutes > 0
                ? `Пакет · использовано ${sessionSnapshot.meter.package_minutes} мин`
                : "Поминутно"}
              {" · "}списано{" "}
              {(sessionSnapshot.meter.billed_cents / 100).toLocaleString(
                "ru-RU",
              )}{" "}
              ₽{" · "}
              {sessionSnapshot.meter.billed_minutes} мин
              {" · "}
              {sessionSnapshot.meter.status === "exhausted"
                ? "баланс исчерпан"
                : "активно"}
            </small>
          )}
        </div>
      </div>
      <div className="panel-section rounded-xl border border-primary/15! bg-base-100/35! p-4">
        <div className="detail-row flex items-center rounded-xl justify-between gap-3 border-b border-primary/10! py-2 px-5 mb-1 text-sm">
          <span className="text-base-content/60!">Группа</span>
          <strong>{pc.group}</strong>
        </div>
        <div className="detail-row flex items-center rounded-xl justify-between gap-3 border-b border-primary/10! py-2 px-5 mb-1 text-sm">
          <span className="text-base-content/60!">Позиция на карте</span>
          <strong>{pc.position ?? "—"}</strong>
        </div>
        <div className="detail-row flex items-center rounded-xl justify-between gap-3 border-b border-primary/10! py-2 px-5 mb-1 text-sm">
          <span className="text-base-content/60!">Устройство</span>
          <strong>{pc.name}</strong>
        </div>
        {isXbox && sessionSnapshot?.session.expires_at && (
          <div className="detail-row flex items-center justify-between gap-3 py-2 text-sm">
            <span className="text-base-content/60!">Завершение</span>
            <strong>{new Date(sessionSnapshot.session.expires_at).toLocaleTimeString("ru-RU")}</strong>
          </div>
        )}
        {sessionSnapshot?.active_entitlement && (
          <div className="detail-row flex items-center justify-between gap-3 py-2 text-sm">
            <span className="text-base-content/60!">Активный пакет</span>
            <strong>
              {sessionSnapshot.active_entitlement.remaining_minutes} мин
              осталось
            </strong>
          </div>
        )}
      </div>
      {sessionSnapshot &&
        sessionSnapshot.entitlements.some(
          (item) => item.status === "queued",
        ) && (
          <div className="rounded-xl border border-primary/15! bg-base-100/35! p-4">
            <div className="mb-3">
              <h3 className="font-semibold">Очередь пакетов</h3>
              <p className="text-xs text-base-content/60!">
                Следующие пакеты активируются по порядку
              </p>
            </div>
            <div className="flex flex-col gap-1">
              {sessionSnapshot.entitlements
                .filter((item) => item.status === "queued")
                .map((item) => (
                  <div
                    className="flex items-center justify-between gap-3 border-t border-primary/10! py-2 text-sm"
                    key={item.id}
                  >
                    <span className="text-base-content/70!">
                      #{item.queue_position} · {item.remaining_minutes} мин
                    </span>
                    <strong className="text-primary!">В очереди</strong>
                  </div>
                ))}
            </div>
          </div>
        )}
      {(pc.status === "online" || pc.status === "busy") && (
        <button
          type="button"
          className="sale-entry-card btn btn-ghost flex w-full h-auto items-center gap-3 rounded-xl border border-primary/30! bg-primary/10! p-3 text-left"
          onClick={onOpenSale}
        >
          <div className="sale-entry-icon grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary! text-primary-content!">
            <Receipt size={20} />
          </div>
          <div className="min-w-0 grow">
            <strong className="block mb-1">Оформить продажу</strong>
            <span className="block text-xs text-base-content/40!">
              Время, товары и покупатель — в одном окне
            </span>
          </div>
          <ChevronRight size={17} />
        </button>
      )}
      <div className="panel-actions pc-panel-actions flex flex-col gap-2">
        {!isXbox && pc.status === "busy" && client && (
          <button
            className="secondary-button wide btn btn-outline"
            onClick={() =>
              onDeposit(
                client,
                false,
                pc.sessionId && pc.deviceId
                  ? {
                      sessionId: pc.sessionId,
                      deviceId: pc.deviceId,
                      workstationName: pc.name,
                    }
                  : undefined,
              )
            }
          >
            <WalletCards size={15} /> Пополнить депозит
          </button>
        )}
        <button
          className="secondary-button wide btn btn-outline"
          onClick={onEdit}
        >
          <Settings size={15} /> {isXbox ? "Редактировать Xbox" : "Редактировать ПК"}
        </button>
        <div className="pc-session-actions flex flex-col gap-2 rounded-lg border border-primary/15! bg-base-200/45! p-3">
          {hasActiveSession && (
            <p className="pc-session-note m-0 text-xs text-base-content/60!">
              Управление сессией
            </p>
          )}
          {hasActiveSession && pc.sessionId && (
            <button
              className="danger-button wide btn btn-error btn-outline"
              onClick={() => void interruptSession()}
              disabled={submitting || !api}
            >
              Прервать сессию
            </button>
          )}
          {!isXbox && (<button
            className="danger-button wide btn btn-error btn-outline"
            onClick={() => void dispatchDeviceCommand("system.restart")}
            disabled={
              submitting ||
              !api ||
              pc.status === "maintenance" ||
              pc.status === "offline"
            }
          >
            Перезапустить ПК
          </button>)}
        </div>
        {!isXbox && (<button
          className="secondary-button wide btn btn-outline"
          onClick={onBook}
          disabled={pc.status !== "online"}
        >
          Забронировать место
        </button>)}
        {operationState && (
          <div
            className={`${operationSuccess ? "form-success border-success/40! bg-success/10! text-success-content!" : "form-error border-error/40! bg-error/10! text-error-content!"} command-result rounded-lg border p-3 text-sm`}
            role={operationSuccess ? "status" : "alert"}
            aria-live="polite"
          >
            {operationState}
          </div>
        )}
      </div>
      <button
        className="danger-button btn btn-error btn-outline"
        onClick={() => void toggleAvailability()}
        disabled={!api || submitting}
        aria-disabled={!api}
      >
        {pc.status === "maintenance" ? "Включить место" : "Отключить место"}{" "}
        <ChevronRight size={15} />
      </button>
      <button
        className="danger-button btn btn-error btn-outline"
        onClick={() => void deleteWorkstation()}
        disabled={!api || submitting}
      >
        Удалить из карты
      </button>
    </div>
  );
}
