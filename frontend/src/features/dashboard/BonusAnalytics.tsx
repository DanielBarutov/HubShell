import { useEffect, useState } from "react";
import type { BackendBonusReport, GameClubApi } from "../../api";

export function BonusAnalytics({ api, startAt, endAt, refreshGeneration }: {
  api: GameClubApi; startAt: string; endAt: string; refreshGeneration: number;
}) {
  const [report, setReport] = useState<BackendBonusReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setReport(null); setError(null);
    if (typeof api.getBonusReport !== "function") return;
    void api.getBonusReport(startAt, endAt).then((value) => {
      if (active) setReport(value);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "Не удалось загрузить бонусный отчёт");
    });
    return () => { active = false; };
  }, [api, startAt, endAt, refreshGeneration, attempt]);
  const amount = (cents: number) => (cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 });
  return <section aria-label="Бонусная программа" className="card bg-base-100 border border-base-300 my-4">
    <div className="card-body gap-3 p-4">
      <h2 className="card-title text-lg">Бонусная программа</h2>
      <p className="text-sm text-base-content/60">Весь клуб. Учитывается выбранный период; дополнительные фильтры продаж не применяются. Суммы в бонусах, отдельно от денежной выручки.</p>
      {typeof api.getBonusReport !== "function" ? <p role="status">Бонусный отчёт недоступен</p>
        : error ? <div role="alert" className="alert alert-error"><span>{error}</span><button className="btn btn-sm" type="button" onClick={() => setAttempt(value => value + 1)}>Повторить загрузку бонусов</button></div>
        : !report ? <p role="status">Загружаем бонусный отчёт…</p>
        : <>
          <h3 className="font-semibold">За выбранный период</h3>
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {([
              ["Зачислено бонусов", report.period.credited_cents],
              ["Оплачено бонусами", report.period.spent_cents],
              ["Ручные корректировки", report.period.adjustments_cents],
              ["Перенос начальных остатков", report.period.opening_cents],
              ["Зарезервировано за период", report.period.reserved_in_cents],
              ["Освобождено из резерва", report.period.released_cents],
            ] as const).map(([label, value]) => <div key={label}><dt className="text-sm text-base-content/60">{label}</dt><dd className="font-semibold tabular-nums">{amount(value)}</dd></div>)}
          </dl>
          <h3 className="font-semibold">Остатки на {new Date(report.observed_at).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })} (Москва)</h3>
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {([
              ["Всего на счетах", report.total_cents],
              ["Доступно", report.available_cents],
              ["Зарезервировано для игры", report.reserved_cents],
              ["Ожидает начисления", report.pending_cents],
            ] as const).map(([label, value]) => <div key={label}><dt className="text-sm text-base-content/60">{label}</dt><dd className="font-semibold tabular-nums">{amount(value)}</dd></div>)}
          </dl>
        </>}
    </div>
  </section>;
}
