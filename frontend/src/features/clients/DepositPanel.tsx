import { useEffect, useState } from "react";
import { ChevronRight, Search, ShieldCheck } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client } from "../../types";

export function DepositPanel({
  initialClient,
  bonusOnly = false,
  onClose,
  onCompleted,
  clients: clientList,
  api,
}: {
  initialClient?: Client;
  bonusOnly?: boolean;
  onClose: () => void;
  onCompleted: () => void;
  clients: Client[];
  api?: GameClubApi;
}) {
  const [query, setQuery] = useState(initialClient?.nickname ?? "");
  const [amount, setAmount] = useState("1000");
  const [bonusAmount, setBonusAmount] = useState(bonusOnly ? "100" : "0");
  const [depositPaymentMethod, setDepositPaymentMethod] = useState("cash");
  const [liveResult, setLiveResult] = useState<Client | undefined>(initialClient);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const normalized = query.trim().toLowerCase();
  const searchField = getSearchField(normalized);
  const ready = searchField !== null;

  useEffect(() => {
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
  }, [api, normalized, searchField]);

  const result = api
    ? liveResult
    : ready
      ? clientList.find((client) => client.nickname.toLowerCase().includes(normalized) || client.phone.replace(/\D/g, "").includes(normalized.replace(/\D/g, "")))
      : undefined;

  const submit = async () => {
    if (!result) {
      return;
    }
    if (!api) {
      onCompleted();
      return;
    }
    const amountCents = Math.round(Number(amount.replace(",", ".")) * 100);
    const parsedBonus = Math.round(Number(bonusAmount.replace(",", ".")));
    if ((!bonusOnly && (!Number.isFinite(amountCents) || amountCents <= 0)) || !Number.isFinite(parsedBonus) || parsedBonus < 0 || (bonusOnly && parsedBonus <= 0)) {
      setSearchError(bonusOnly ? "Введите положительное количество бонусов" : "Введите положительную сумму");
      return;
    }
    setSubmitting(true);
    setSearchError(null);
    try {
      await api.topUp(
        result.id,
        {
          amount_cents: bonusOnly ? 0 : amountCents,
          bonus_amount: parsedBonus,
          reason: bonusOnly ? "Начисление бонусов через оператора" : "Пополнение через оператора",
          payment_parts: bonusOnly
            ? undefined
            : [{ method: depositPaymentMethod, amount_cents: amountCents }],
        },
        crypto.randomUUID(),
      );
      onCompleted();
    } catch (error) {
      setSearchError(error instanceof ApiError ? error.message : "Не удалось пополнить депозит");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title={bonusOnly ? "Начисление бонусов" : "Пополнение депозита"} subtitle="Баланс клиента" onClose={onClose} /><div className="deposit-step"><span className="step-label">1 / 2</span><h2>Найдите клиента</h2><p>Введите минимум 3 символа ника или 4 цифры телефона.</p><div className="search-box panel-search"><Search size={17} /><input aria-label="Ник или номер телефона" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ник или номер телефона" /></div>{ready && result && <div className="client-result"><div className="client-avatar">{result.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{result.nickname}</strong><span>{formatRussianPhone(result.phone)}</span></div><ChevronRight size={16} /></div>}{ready && !result && <div className="empty-result" role="status" aria-live="polite">{searchError || "Клиент не найден"}</div>}</div><div className="deposit-preview"><div><span>{bonusOnly ? "Бонусы будут начислены на" : "Средства будут зачислены на"}</span><strong>{result?.nickname || "—"}</strong></div><ShieldCheck size={21} /></div>{!bonusOnly && <><label className="amount-field">Сумма пополнения<input aria-label="Сумма пополнения в рублях" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /> <span>₽</span></label><label>Способ оплаты<select value={depositPaymentMethod} onChange={(event) => setDepositPaymentMethod(event.target.value)}><option value="cash">Наличные</option><option value="card">Карта</option><option value="transfer">Перевод</option></select></label></>}<label className="amount-field">Бонусы<input aria-label="Количество бонусов" inputMode="numeric" value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /> <span>шт.</span></label>{searchError && result && <div className="form-error" role="alert">{searchError}</div>}<button className="primary-button wide" disabled={!result || submitting} onClick={() => void submit()}>{submitting ? "Зачисляем..." : bonusOnly ? "Начислить бонусы" : "Зачислить депозит"}</button><button className="secondary-button wide" onClick={onClose}>Отмена</button></div>;
}
