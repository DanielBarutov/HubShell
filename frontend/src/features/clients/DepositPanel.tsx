import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client, Workstation } from "../../types";
import type { DepositTarget } from "../workspace/uiSlice";
import { findActiveDepositTargets } from "./depositTarget";

export function DepositPanel({
  initialClient,
  bonusOnly = false,
  target,
  cashShiftId,
  workstations,
  onClose,
  onCompleted,
  clients: clientList,
  api,
}: {
  initialClient?: Client;
  bonusOnly?: boolean;
  target?: DepositTarget;
  cashShiftId?: string;
  workstations: Workstation[];
  onClose: () => void;
  onCompleted: (closePanel?: boolean) => void | Promise<void>;
  clients: Client[];
  api?: GameClubApi;
}) {
  const [query, setQuery] = useState(initialClient?.nickname ?? "");
  const [amount, setAmount] = useState("1000");
  const [bonusAmount, setBonusAmount] = useState(bonusOnly ? "100" : "0");
  const [bonusReason, setBonusReason] = useState("");
  const [pendingBonusAdjustment, setPendingBonusAdjustment] = useState<{ clientId: string; amountCents: number; reason: string; key: string } | null>(null);
  const [depositPaymentMethod, setDepositPaymentMethod] = useState<"cash" | "transfer" | "mixed">("cash");
  const [cashPartAmount, setCashPartAmount] = useState("");
  const [transferPartAmount, setTransferPartAmount] = useState("");
  const [liveResult, setLiveResult] = useState<Client | undefined>(initialClient);
  const [selectedSessionId, setSelectedV2SessionId] = useState(target?.sessionId ?? "");
  const [recipientChangeConfirmed, setRecipientChangeConfirmed] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [deliveryMessage, setDeliveryMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const normalized = query.trim().toLowerCase();
  const normalizedDigits = normalized.replace(/\D/g, "");
  const searchField = getSearchField(normalized);
  const ready = searchField !== null;

  useEffect(() => {
    if (pendingBonusAdjustment) return undefined;
    if (target) {
      setLiveResult(initialClient);
      return undefined;
    }
    if (!api) {
      setLiveResult(undefined);
      return undefined;
    }
    if (!searchField) {
      setLiveResult(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(normalized, searchField);
        if (active) {
          setLiveResult(found[0] ? toUiClient(found[0]) : undefined);
          setSearchError(null);
        }
      } catch (error) {
        if (active) {
          setSearchError(error instanceof ApiError ? error.message : "Не удалось выполнить поиск");
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, initialClient, normalized, searchField, target, pendingBonusAdjustment]);

  const result = api
    ? liveResult
    : ready
      ? clientList.find((client) => client.nickname.toLowerCase().includes(normalized) || (normalizedDigits.length > 0 && client.phone.replace(/\D/g, "").includes(normalizedDigits)))
      : undefined;
  const activeTargets = bonusOnly || !result
    ? []
    : findActiveDepositTargets(result.id, workstations);
  const validSelectedSessionId = activeTargets.some((target) =>
    target.sessionId === selectedSessionId)
    ? selectedSessionId
    : "";
  const depositTarget = bonusOnly ? undefined : target
    ?? (activeTargets.length === 1
      ? activeTargets[0]
      : activeTargets.find((target) => target.sessionId === validSelectedSessionId));
  const requiresTargetSelection = !target
    && activeTargets.length > 1
    && !depositTarget;
  const recipientChanged = !depositTarget && Boolean(initialClient && result && result.id !== initialClient.id);

  const submit = async () => {
    if (!result) {
      return;
    }
    if (requiresTargetSelection) {
      setSearchError("Выберите игровое место для пополнения");
      return;
    }
    if (recipientChanged && !recipientChangeConfirmed) {
      setSearchError("Подтвердите смену получателя");
      return;
    }
    if (bonusOnly) {
      const normalizedBonus = bonusAmount.trim().replace(",", ".");
      if (!/^-?\d+(\.\d{1,2})?$/.test(normalizedBonus)) {
        setSearchError("Введите ненулевую сумму бонусов с точностью до 0,01"); return;
      }
      const [whole, fraction = ""] = normalizedBonus.replace("-", "").split(".");
      const amountCents = (Number(whole) * 100 + Number(fraction.padEnd(2, "0"))) * (normalizedBonus.startsWith("-") ? -1 : 1);
      if (!Number.isSafeInteger(amountCents) || amountCents === 0 || !bonusReason.trim()) {
        setSearchError("Укажите ненулевую сумму и причину корректировки"); return;
      }
      if (!api) { setDeliveryMessage("Демо: корректировка не отправлена на сервер"); return; }
      if (!pendingBonusAdjustment && amountCents < 0 && !window.confirm(
        `Списать ${(Math.abs(amountCents) / 100).toLocaleString("ru-RU")} бонусов у «${result.nickname}»?\nПричина: ${bonusReason.trim()}`,
      )) return;
      const operation = pendingBonusAdjustment ?? { clientId: result.id, amountCents, reason: bonusReason.trim(), key: crypto.randomUUID() };
      setPendingBonusAdjustment(operation);
      setSubmitting(true);
      setSearchError(null);
      try {
        await api.adjustBonus(operation.clientId, operation.amountCents, operation.reason, operation.key);
        setDeliveryMessage("Корректировка бонусов сохранена");
        setPendingBonusAdjustment(null);
        try { await onCompleted(false); } catch { setSearchError("Корректировка сохранена, но данные клиента не удалось обновить"); }
      } catch (error) {
        if (!pendingBonusAdjustment && error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) setPendingBonusAdjustment(null);
        setSearchError(error instanceof ApiError ? error.message : "Нет подтверждения сервера. Повторите сохранённую корректировку.");
      } finally { setSubmitting(false); }
      return;
    }
    if (!api) {
      await onCompleted();
      return;
    }
    const amountCents = Math.round(Number(amount.replace(",", ".")) * 100);
    const parsedBonus = Number(bonusAmount.replace(",", "."));
    if (!Number.isFinite(amountCents) || amountCents <= 0 || !Number.isInteger(parsedBonus) || parsedBonus < 0) {
      setSearchError("Введите положительную сумму и целое количество бонусов. Для дробных бонусов используйте корректировку.");
      return;
    }
    const cashPartCents = Math.round(Number(cashPartAmount.replace(",", ".")) * 100);
    const transferPartCents = Math.round(Number(transferPartAmount.replace(",", ".")) * 100);
    if (!bonusOnly && depositPaymentMethod === "mixed" && (
      !Number.isInteger(cashPartCents)
      || !Number.isInteger(transferPartCents)
      || cashPartCents <= 0
      || transferPartCents <= 0
      || cashPartCents + transferPartCents !== amountCents
    )) {
      setSearchError("Укажите положительные части наличными и переводом, равные сумме пополнения");
      return;
    }
    setSubmitting(true);
    setSearchError(null);
    try {
      const paymentParts = depositPaymentMethod === "mixed"
        ? [
          { method: "cash", amount_cents: cashPartCents },
          { method: "transfer", amount_cents: transferPartCents },
        ]
        : [{ method: depositPaymentMethod, amount_cents: amountCents }];
      if (depositTarget) {
        if (paymentParts.some((part) => part.method === "cash") && !cashShiftId) {
          setSearchError("Чтобы принять наличные, откройте кассовую смену или выберите перевод.");
          setSubmitting(false);
          return;
        }
        const deposit = await api.createV2Deposit(
          result.id,
          {
            session_id: depositTarget.sessionId,
            device_id: depositTarget.deviceId,
            amount_cents: amountCents,
            currency: "RUB",
            reason: "Пополнение через оператора",
            payment_parts: paymentParts,
            cash_shift_id: paymentParts.some((part) => part.method === "cash")
              ? cashShiftId
              : undefined,
          },
          crypto.randomUUID(),
        );
        setDeliveryMessage(deposit.is_duplicate
          ? "Пополнение уже учтено. Повторно деньги не списаны."
          : "Пополнение оформлено. Баланс обновится, когда компьютер будет на связи.");
        await onCompleted(false);
        return;
      }
      await api.topUp(
        result.id,
        {
          amount_cents: amountCents,
          bonus_amount: parsedBonus,
          reason: "Пополнение через оператора",
          payment_parts: paymentParts,
        },
        crypto.randomUUID(),
      );
      await onCompleted();
    } catch (error) {
      setSearchError(error instanceof ApiError ? error.message : "Не удалось пополнить депозит");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner deposit-panel flex flex-col gap-4 p-5">
    <PanelHeader title={bonusOnly ? "Корректировка бонусов" : "Пополнение депозита"} subtitle="Баланс клиента" onClose={onClose} />
    <section className="deposit-step flex flex-col gap-3">
      <h2>{requiresTargetSelection ? "Выберите игровое место" : depositTarget ? "Пополнение игрового счёта" : "Найдите клиента"}</h2>
      <p>{requiresTargetSelection
        ? "У клиента открыто несколько игр. Выберите компьютер для зачисления."
        : depositTarget
          ? "Зачислим средства на баланс выбранного клиента."
          : "Введите имя или номер телефона."}</p>
      <div className="search-box panel-search input input-sm flex items-center gap-2 border-primary/20! bg-base-200/55! shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"><Search size={17} /><input className="grow input input-sm" aria-label="Ник или номер телефона" autoFocus={!depositTarget} value={query} disabled={Boolean(depositTarget) || Boolean(pendingBonusAdjustment)} onChange={(event) => { setQuery(event.target.value); setRecipientChangeConfirmed(false); }} placeholder="Ник или номер телефона" /></div>
      {ready && result && <div className="client-result flex items-center gap-3 rounded-lg border border-primary/20! bg-base-200/55! p-3"><div className="client-avatar grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary! text-sm font-bold text-primary-content!">{result.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{result.nickname}</strong><span>{formatRussianPhone(result.phone)}</span></div></div>}
      {ready && !result && <div className="empty-result rounded-lg border border-primary/20! bg-base-200/55! p-3 text-sm text-base-content/60!" role="status" aria-live="polite">{searchError || "Клиент не найден"}</div>}
    </section>
    {!target && activeTargets.length > 1 && <label className="amount-field deposit-target-field">Игровое место
        <select className="select select-sm"
        aria-label="Игровое место"
        value={validSelectedSessionId}
        onChange={(event) => setSelectedV2SessionId(event.target.value)}
      >
        <option value="">Выберите ПК</option>
        {activeTargets.map((target) => (
          <option key={target.sessionId} value={target.sessionId}>
            {target.workstationName}
          </option>
        ))}
      </select>
    </label>}
    {depositTarget && (target || activeTargets.length === 1) && <div className="deposit-session-route flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-xs text-base-content/60!"><span>Игровое место</span><strong>{depositTarget.workstationName}</strong></div>}
    {recipientChanged && <label className="settings-checkbox mt-2 flex cursor-pointer items-center gap-3 text-sm"><input className="toggle toggle-primary toggle-sm" type="checkbox" checked={recipientChangeConfirmed} onChange={(event) => setRecipientChangeConfirmed(event.target.checked)} /> Подтверждаю смену получателя с «{initialClient?.nickname}» на «{result?.nickname}»</label>}
    {result && !deliveryMessage && <div className="deposit-fields flex flex-col gap-3 border-t border-primary/15! pt-4">
      {!bonusOnly && <>
        <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Сумма пополнения<input className="input input-sm" aria-label="Сумма пополнения в рублях" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /> <span>₽</span></label>
        <label className="amount-field deposit-payment-field">Способ оплаты<select className="select select-sm" value={depositPaymentMethod} onChange={(event) => { const method = event.target.value as "cash" | "transfer" | "mixed"; setDepositPaymentMethod(method); if (method === "mixed") { const half = (Math.round(Number(amount.replace(",", ".")) * 100) / 200).toFixed(2); setCashPartAmount(half); setTransferPartAmount(half); } }}><option value="cash">Наличные</option><option value="transfer">Перевод</option><option value="mixed">Смешанная оплата</option></select></label>
        {depositPaymentMethod === "mixed" && <div className="deposit-payment-parts grid grid-cols-1 gap-3 md:grid-cols-2"><label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Наличными<input className="input input-sm" aria-label="Сумма наличными" inputMode="decimal" value={cashPartAmount} onChange={(event) => setCashPartAmount(event.target.value)} /> <span>₽</span></label><label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Переводом<input className="input input-sm" aria-label="Сумма переводом" inputMode="decimal" value={transferPartAmount} onChange={(event) => setTransferPartAmount(event.target.value)} /> <span>₽</span></label></div>}
        {!depositTarget && activeTargets.length === 0 && <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Бонусы<input className="input input-sm" aria-label="Количество бонусов" inputMode="numeric" value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /> <span>шт.</span></label>}
      </>}
      {bonusOnly && <div className="col-span-full flex flex-col gap-3">
        <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Бонусы<input className="input input-sm" aria-label="Количество бонусов" inputMode="decimal" disabled={Boolean(pendingBonusAdjustment)} value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /></label>
        <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">Причина корректировки<input className="input input-sm w-full" maxLength={255} disabled={Boolean(pendingBonusAdjustment)} value={bonusReason} onChange={(event) => setBonusReason(event.target.value)} /></label>
        <p className="text-xs text-base-content/60">1 бонус = 1 ₽. Для списания введите отрицательную сумму. Резерв игры не затрагивается.</p>
        {pendingBonusAdjustment && <p role="status" className="text-xs text-warning">Данные сохранены для повтора с тем же ключом до подтверждения результата.</p>}
      </div>}
    </div>}
    {deliveryMessage && <div className="form-success rounded-lg border border-success/40! bg-success/10! p-3 text-sm text-success-content!" role="status" aria-live="polite">{deliveryMessage}</div>}
    {searchError && result && <div className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!" role="alert">{searchError}</div>}
    {deliveryMessage
      ? <button className="primary-button btn btn-primary btn-block wide w-full bg-primary! text-primary-content!" onClick={onClose}>Готово</button>
      : <>
        <button className="primary-button btn btn-primary btn-block wide w-full bg-primary! text-primary-content!" disabled={!result || submitting || requiresTargetSelection || (recipientChanged && !recipientChangeConfirmed)} onClick={() => void submit()}>{submitting ? bonusOnly ? "Сохраняем..." : "Зачисляем..." : bonusOnly ? pendingBonusAdjustment ? "Повторить корректировку" : bonusAmount.trim().startsWith("-") ? "Списать бонусы" : "Начислить бонусы" : "Зачислить депозит"}</button>
        <button className="secondary-button btn btn-outline btn-block wide w-full" onClick={onClose}>Отмена</button>
      </>}
  </div>;
}
