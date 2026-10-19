import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { GameClubApi } from "../../api";
import type { BackendClientUpdateStatus, ClientUpdateDeviceStatus } from "../../api";
import type { Workstation } from "../../types";

const phases = {
  polling: "Ожидаем готовность ПК",
  preparing: "Подготовка обновления",
  authorized: "Обновление клиентов",
  failed: "Ошибка доставки",
  completed: "Доставка завершена",
};
const statuses: Record<ClientUpdateDeviceStatus, string> = {
  confirmed: "Обновлён", unreachable: "Нет свежего ответа", failed: "Ошибка",
  rolled_back: "Выполнен откат", active_session: "Идёт сеанс", pending_facts: "Ожидаем сверку",
  not_ready: "Не готов", waiting_gui: "Ожидаем запуск клиента", ready: "Готов",
  installing: "Замена файла", verifying: "Проверка запуска",
};

export function ClientUpdateStatus({ api, pcs }: { api: GameClubApi; pcs: Workstation[] }) {
  const [data, setData] = useState<BackendClientUpdateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;
    setLoading(true);
    setError(null);
    async function poll() {
      const request = new AbortController();
      controller = request;
      const deadline = setTimeout(() => request.abort(), 10000);
      try {
        const current = await api.getClientUpdateStatus(request.signal);
        if (active) { setData(current); setError(null); }
      } catch (reason) {
        if (active) {
          setData(null);
          setError(request.signal.aborted ? "Сервер не отвечает" : reason instanceof Error ? reason.message : "Не удалось получить статус доставки");
        }
      } finally {
        clearTimeout(deadline);
        if (active) { setLoading(false); timer = setTimeout(() => void poll(), 5000); }
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); controller?.abort(); };
  }, [api, reload]);

  const delivery = data?.deployment;
  return <section className="card card-border mb-4 border-primary/15 bg-base-100/70" aria-label="Обновления клиентов">
    <div className="card-body gap-4 p-4 sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="card-title text-base"><Download size={18} aria-hidden="true" />Обновления клиентов</h2>
        <button type="button" className="btn btn-sm btn-ghost" disabled={loading}
          onClick={() => setReload((value) => value + 1)} aria-label="Обновить статус доставки">
          <RefreshCw size={14} aria-hidden="true" />Обновить
        </button>
      </div>
      {loading && <p role="status" className="text-sm text-base-content/65">Загружаем статус обновления…</p>}
      {error && <p role="alert" className="alert alert-error alert-soft text-sm">Статус недоступен: {error}</p>}
      {!loading && data && !delivery && <p className="text-sm text-base-content/65">Доставок ещё не было.</p>}
      {!loading && delivery && <>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="break-all font-medium">{delivery.release_id}</p>
            <p className="text-xs text-base-content/60">Начато {new Date(delivery.created_at).toLocaleString("ru-RU")}</p></div>
          <span className={`badge badge-soft ${delivery.phase === "failed" ? "badge-error" : delivery.phase === "completed" ? "badge-success" : "badge-info"}`}>
            {phases[delivery.phase]}
          </span>
        </div>
        <p className="text-sm">Подтверждено обновление: <strong>{delivery.confirmed}/{delivery.total} ПК</strong></p>
        <p className="text-xs text-base-content/60">Состояние на {new Date(delivery.observed_at).toLocaleString("ru-RU")}</p>
        {delivery.phase === "failed" ? <p className="text-sm text-error">Парк остаётся закрытым до устранения ошибки.</p>
          : delivery.phase === "polling" ? <p className="text-sm text-base-content/65">Занятый или недоступный ПК задерживает обновление всего парка.</p>
          : delivery.phase !== "completed" && <p className="text-sm text-base-content/65">Новые сеансы заблокированы на время обновления.</p>}
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <caption className="sr-only">Состояние обновления каждого ПК</caption>
            <thead><tr><th>ПК</th><th>Версия клиента</th><th>Состояние</th><th>Последний ответ</th></tr></thead>
            <tbody>{delivery.devices.map((device) => <tr key={device.device_id}>
              <th>{pcs.find((pc) => pc.id === device.workstation_id)?.name ?? device.device_id}</th>
              <td><span>{device.old_release_id ?? "—"} → {device.running_release_id ?? "—"}</span></td>
              <td><span>{statuses[device.status] ?? "Неизвестно"}</span>
                {device.error_code && <p className="text-xs text-error">Код: {device.error_code}</p>}</td>
              <td>{device.received_at ? <time dateTime={device.received_at}>{new Date(device.received_at).toLocaleTimeString("ru-RU")}</time> : "—"}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
    </div>
  </section>;
}
