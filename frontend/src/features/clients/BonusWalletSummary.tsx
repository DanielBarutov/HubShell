import { useEffect, useState } from "react";
import { GameClubApi } from "../../api";
import type { BackendBonusWallet, BackendBonusOperation } from "../../api";

export function BonusWalletSummary({ api, clientId }: { api: GameClubApi; clientId: string }) {
  const [wallet, setWallet] = useState<BackendBonusWallet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<BackendBonusOperation[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const loadHistory = async () => {
    setHistoryOpen(true); setHistory(null); setHistoryError(null);
    try { setHistory(await api.listBonusOperations(clientId)); }
    catch (cause) { setHistoryError(cause instanceof Error ? cause.message : "Не удалось загрузить историю бонусов"); }
  };
  useEffect(() => {
    let active = true;
    setWallet(null);
    setError(null);
    void api.getBonusWallet(clientId).then((value) => { if (active) setWallet(value); }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Не удалось загрузить бонусы"); });
    return () => { active = false; };
  }, [api, clientId, attempt]);

  if (error) return <div role="alert" className="alert alert-error mt-3 text-sm"><span>{error}</span><button type="button" className="btn btn-sm" onClick={() => setAttempt((value) => value + 1)}>Обновить бонусы</button></div>;
  if (!wallet) return <p role="status" className="mt-3 text-sm"><span className="loading loading-spinner loading-xs mr-2" />Загружаем бонусы…</p>;
  return <><dl className="mt-3 grid grid-cols-2 gap-2 text-sm" aria-label="Бонусный счёт">
    {([
      ["Доступно бонусов", wallet.available_cents],
      ["Ожидает начисления", wallet.pending_cents],
      ["Зарезервировано для игры", wallet.reserved_cents],
      ["Всего на бонусном счёте", wallet.total_cents],
    ] as const).map(([label, cents]) => <div key={label} className="contents"><dt>{label}</dt><dd className="text-right font-semibold">{(cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 })} ₽</dd></div>)}
  </dl>
    <button type="button" className="btn btn-ghost btn-sm mt-3" onClick={() => historyOpen ? setHistoryOpen(false) : void loadHistory()}>{historyOpen ? "Скрыть историю бонусов" : "История бонусов"}</button>
    {historyOpen && <section aria-label="История бонусов" className="mt-2 text-sm">
      {historyError ? <div role="alert" className="alert alert-error"><span>{historyError}</span><button type="button" className="btn btn-sm" onClick={() => void loadHistory()}>Повторить загрузку истории</button></div>
        : history === null ? <p role="status">Загружаем историю…</p>
        : history.length === 0 ? <p>Бонусных операций пока нет</p>
        : <ul className="space-y-3">{history.map((operation) => <li key={operation.id} className="border-t border-primary/15 pt-2 break-words">
          <p className="font-semibold">{operation.reason}</p>
          <p>Бонусы: {operation.total_delta_cents > 0 ? "+" : ""}{(operation.total_delta_cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 })} ₽ · резерв: {(operation.reserved_delta_cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 })} ₽</p>
          <p className="text-xs text-base-content/60">{new Date(operation.created_at).toLocaleString("ru-RU")} · Автор: {operation.actor_id}</p>
        </li>)}</ul>}
    </section>}
  </>;
}
