import { useEffect, useState } from "react";
import { ChevronRight, Search, ShieldCheck } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client } from "../../types";
import type { V2DepositTarget } from "../workspace/uiSlice";

export function DepositPanel({
  initialClient,
  bonusOnly = false,
  v2Target,
  onClose,
  onCompleted,
  clients: clientList,
  api,
}: {
  initialClient?: Client;
  bonusOnly?: boolean;
  v2Target?: V2DepositTarget;
  onClose: () => void;
  onCompleted: (closePanel?: boolean) => void | Promise<void>;
  clients: Client[];
  api?: GameClubApi;
}) {
  const [query, setQuery] = useState(initialClient?.nickname ?? "");
  const [amount, setAmount] = useState("1000");
  const [bonusAmount, setBonusAmount] = useState(bonusOnly ? "100" : "0");
  const [depositPaymentMethod, setDepositPaymentMethod] = useState<"cash" | "transfer" | "mixed">("cash");
  const [cashPartAmount, setCashPartAmount] = useState("");
  const [transferPartAmount, setTransferPartAmount] = useState("");
  const [liveResult, setLiveResult] = useState<Client | undefined>(initialClient);
  const [recipientChangeConfirmed, setRecipientChangeConfirmed] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [deliveryMessage, setDeliveryMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const normalized = query.trim().toLowerCase();
  const normalizedDigits = normalized.replace(/\D/g, "");
  const searchField = getSearchField(normalized);
  const ready = searchField !== null;

  useEffect(() => {
    if (v2Target) {
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
  }, [api, initialClient, normalized, searchField, v2Target]);

  const result = api
    ? liveResult
    : ready
      ? clientList.find((client) => client.nickname.toLowerCase().includes(normalized) || (normalizedDigits.length > 0 && client.phone.replace(/\D/g, "").includes(normalizedDigits)))
      : undefined;
  const recipientChanged = !v2Target && Boolean(initialClient && result && result.id !== initialClient.id);

  const submit = async () => {
    if (!result) {
      return;
    }
    if (recipientChanged && !recipientChangeConfirmed) {
      setSearchError("Подтвердите смену получателя");
      return;
    }
    if (!api) {
      await onCompleted();
      return;
    }
    const amountCents = Math.round(Number(amount.replace(",", ".")) * 100);
    const parsedBonus = Math.round(Number(bonusAmount.replace(",", ".")));
    if ((!bonusOnly && (!Number.isFinite(amountCents) || amountCents <= 0)) || !Number.isFinite(parsedBonus) || parsedBonus < 0 || (bonusOnly && parsedBonus <= 0)) {
      setSearchError(bonusOnly ? "Введите положительное количество бонусов" : "Введите положительную сумму");
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
      if (v2Target) {
        const deposit = await api.createV2Deposit(
          result.id,
          {
            session_id: v2Target.sessionId,
            device_id: v2Target.deviceId,
            amount_cents: amountCents,
            currency: "RUB",
            reason: "Пополнение автономной сессии через оператора",
            payment_parts: paymentParts,
          },
          crypto.randomUUID(),
        );
        setDeliveryMessage(deposit.is_duplicate
          ? "Это пополнение уже было принято сервером. Повтор не создал вторую операцию; событие ожидает доставки на ПК."
          : "Пополнение принято сервером. Событие ожидает доставки на ПК.");
        await onCompleted(false);
        return;
      }
      await api.topUp(
        result.id,
        {
          amount_cents: bonusOnly ? 0 : amountCents,
          bonus_amount: parsedBonus,
          reason: bonusOnly ? "Начисление бонусов через оператора" : "Пополнение через оператора",
          payment_parts: bonusOnly ? undefined : paymentParts,
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

  return <div className="panel-inner">
    <PanelHeader title={bonusOnly ? "Начисление бонусов" : "Пополнение депозита"} subtitle="Баланс клиента" onClose={onClose} />
    <div className="deposit-step">
      <span className="step-label">1 / 2</span>
      <h2>{v2Target ? "Клиент активной V2-сессии" : "Найдите клиента"}</h2>
      <p>{v2Target ? `Пополнение будет отправлено в сессию на ПК «${v2Target.workstationName}». Получателя менять нельзя.` : "Введите минимум 3 символа ника или 4 цифры телефона."}</p>
      <div className="search-box panel-search"><Search size={17} /><input aria-label="Ник или номер телефона" autoFocus={!v2Target} value={query} disabled={Boolean(v2Target)} onChange={(event) => { setQuery(event.target.value); setRecipientChangeConfirmed(false); }} placeholder="Ник или номер телефона" /></div>
      {ready && result && <div className="client-result"><div className="client-avatar">{result.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{result.nickname}</strong><span>{formatRussianPhone(result.phone)}</span></div><ChevronRight size={16} /></div>}
      {ready && !result && <div className="empty-result" role="status" aria-live="polite">{searchError || "Клиент не найден"}</div>}
    </div>
    <div className="deposit-preview"><div><span>{bonusOnly ? "Бонусы будут начислены на" : "Средства будут зачислены на"}</span><strong>{result?.nickname || "—"}</strong></div><ShieldCheck size={21} /></div>
    {v2Target && <div className="detail-row"><span>Целевая V2-сессия</span><strong>{v2Target.workstationName}</strong></div>}
    {recipientChanged && <label className="settings-checkbox"><input type="checkbox" checked={recipientChangeConfirmed} onChange={(event) => setRecipientChangeConfirmed(event.target.checked)} /> Подтверждаю смену получателя с «{initialClient?.nickname}» на «{result?.nickname}»</label>}
    {!bonusOnly && <>
      <label className="amount-field">Сумма пополнения<input aria-label="Сумма пополнения в рублях" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /> <span>₽</span></label>
      <label>Способ оплаты<select value={depositPaymentMethod} onChange={(event) => { const method = event.target.value as "cash" | "transfer" | "mixed"; setDepositPaymentMethod(method); if (method === "mixed") { const half = (Math.round(Number(amount.replace(",", ".")) * 100) / 200).toFixed(2); setCashPartAmount(half); setTransferPartAmount(half); } }}><option value="cash">Наличные</option><option value="transfer">Перевод</option><option value="mixed">Смешанная: наличные + перевод</option></select></label>
      {depositPaymentMethod === "mixed" && <div className="deposit-payment-parts"><label className="amount-field">Наличными<input aria-label="Сумма наличными" inputMode="decimal" value={cashPartAmount} onChange={(event) => setCashPartAmount(event.target.value)} /> <span>₽</span></label><label className="amount-field">Переводом<input aria-label="Сумма переводом" inputMode="decimal" value={transferPartAmount} onChange={(event) => setTransferPartAmount(event.target.value)} /> <span>₽</span></label></div>}
      {!v2Target && <label className="amount-field">Бонусы<input aria-label="Количество бонусов" inputMode="numeric" value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /> <span>шт.</span></label>}
    </>}
    {bonusOnly && <label className="amount-field">Бонусы<input aria-label="Количество бонусов" inputMode="numeric" value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /> <span>шт.</span></label>}
    {deliveryMessage && <div className="form-success" role="status" aria-live="polite">{deliveryMessage}</div>}
    {searchError && result && <div className="form-error" role="alert">{searchError}</div>}
    <button className="primary-button wide" disabled={!result || submitting || Boolean(deliveryMessage) || (recipientChanged && !recipientChangeConfirmed)} onClick={() => void submit()}>{submitting ? "Зачисляем..." : deliveryMessage ? "Принято сервером" : bonusOnly ? "Начислить бонусы" : "Зачислить депозит"}</button>
    <button className="secondary-button wide" onClick={onClose}>{deliveryMessage ? "Закрыть" : "Отмена"}</button>
  </div>;
}
