import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { GameClubApi } from "../../api";
import type { BackendBonusProgram } from "../../api";
import { generateUUID } from "../../utils/uuid";

const fields = [
  ["game_rate_bps", "Начисление за игру"],
  ["product_rate_bps", "Начисление за товары"],
  ["payment_limit_bps", "Максимальная оплата бонусами"],
] as const;
type RateField = typeof fields[number][0];
type Draft = Record<RateField, string>;

function parsePercent(value: string): number | null {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  const bps = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return bps <= 10000 ? bps : null;
}

export function BonusProgramSettings({ api }: { api: GameClubApi }) {
  const [policy, setPolicy] = useState<BackendBonusProgram | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [draft, setDraft] = useState<Draft>({ game_rate_bps: "", product_rate_bps: "", payment_limit_bps: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  const operationKey = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void api.getBonusProgram().then((result) => {
      if (!active) return;
      setPolicy(result);
      setEnabled(result.enabled);
      setDraft({ game_rate_bps: String(result.game_rate_bps / 100), product_rate_bps: String(result.product_rate_bps / 100), payment_limit_bps: String(result.payment_limit_bps / 100) });
      operationKey.current = null;
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Не удалось загрузить бонусную программу");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, reload]);

  const values = Object.fromEntries(fields.map(([field]) => [field, parsePercent(draft[field])])) as Record<RateField, number | null>;
  const valid = fields.every(([field]) => values[field] !== null);
  const dirty = policy !== null && (enabled !== policy.enabled || fields.some(([field]) => values[field] !== policy[field]));

  function edit() {
    setSaved(false);
    operationKey.current = null;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy || !valid || saving) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    operationKey.current ??= generateUUID();
    try {
      const result = await api.updateBonusProgram({
        enabled, game_rate_bps: values.game_rate_bps!, product_rate_bps: values.product_rate_bps!, payment_limit_bps: values.payment_limit_bps!,
      }, operationKey.current);
      setPolicy(result);
      operationKey.current = null;
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить бонусную программу");
    } finally { setSaving(false); }
  }

  return <section className="card card-border mb-4 border-primary/15 bg-base-100/70" aria-label="Бонусная программа">
    <div className="card-body gap-4 p-4 sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="card-title text-base"><Sparkles size={18} />Бонусная программа</h2>
        <span className="text-xs text-base-content/60">1 бонус = 1 ₽ · без сгорания</span>
      </div>
      {loading ? <p role="status" className="text-sm text-base-content/65"><span className="loading loading-spinner loading-xs mr-2" />Загружаем настройки бонусов…</p> : policy && <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" className="toggle toggle-sm" checked={enabled} disabled={saving} onChange={(event) => { edit(); setEnabled(event.target.checked); }} />
          Бонусная программа включена
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {fields.map(([field, label]) => <label key={field} className="flex flex-col gap-1 text-xs text-base-content/70">
            {label}, %
            <input className="input input-sm w-full" inputMode="decimal" value={draft[field]} disabled={saving}
              aria-invalid={parsePercent(draft[field]) === null}
              onChange={(event) => { edit(); setDraft((current) => ({ ...current, [field]: event.target.value })); }} />
          </label>)}
        </div>
        {!valid && <p role="alert" className="text-sm text-error">Введите проценты от 0 до 100 с точностью до 0,01%.</p>}
        <p className="text-xs leading-relaxed text-base-content/60">Начисление — с денежной части после скидок. Бонусами оплачивается только игровое время. Текущие сессии сохраняют прежние условия.</p>
        {!enabled && <p className="text-xs text-base-content/60">Новые начисления и бонусные оплаты будут выключены. Остатки сохранятся, текущие сессии завершатся по прежним условиям.</p>}
        <div className="card-actions items-center justify-between">
          {saved ? <span role="status" className="text-sm text-success">Настройки бонусов сохранены</span> : <span className="text-xs text-base-content/50">Изменения действуют для новых сессий и продаж</span>}
          <button type="submit" className="btn btn-primary btn-sm" disabled={saving || !valid || !dirty}>{saving ? "Сохраняем…" : "Сохранить бонусную программу"}</button>
        </div>
      </form>}
      {error && <div role="alert" className="alert alert-error alert-soft text-sm"><span>{error}</span><button type="button" className="btn btn-sm btn-ghost" disabled={saving} onClick={() => setReload((value) => value + 1)}>Загрузить заново</button></div>}
    </div>
  </section>;
}
