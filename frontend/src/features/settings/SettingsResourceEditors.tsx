import { useEffect, useState } from "react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendClientGroup, BackendNotificationRule } from "../../api";

export function SettingsResourceEditors({ api, clientGroups, notificationRules, onSaved }: { api: GameClubApi; clientGroups: BackendClientGroup[]; notificationRules: BackendNotificationRule[]; onSaved: () => void }) {
  return <div className="settings-resource-editors"><ClientGroupEditor api={api} groups={clientGroups} onSaved={onSaved} /><NotificationRuleEditor api={api} rules={notificationRules} onSaved={onSaved} /></div>;
}

function ClientGroupEditor({ api, groups, onSaved }: { api: GameClubApi; groups: BackendClientGroup[]; onSaved: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = groups.find((group) => group.id === selectedId);
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [allowNegative, setAllowNegative] = useState(false);
  const [limitRubles, setLimitRubles] = useState("0");
  const [active, setActive] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setId(selected?.id ?? "");
    setName(selected?.name ?? "");
    setAllowNegative(selected?.allow_negative_balance ?? false);
    setLimitRubles(selected ? String(selected.negative_balance_limit_cents / 100) : "0");
    setActive(selected?.active ?? true);
    setIsDefault(selected?.is_default ?? false);
    setError(null);
  }, [selected]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const limit = Number(limitRubles.replace(",", "."));
    if (!id.trim() || !name.trim() || !Number.isFinite(limit) || limit < 0 || (!allowNegative && limit !== 0)) {
      setError("Укажите группу, название и корректный лимит долга");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { name: name.trim(), allow_negative_balance: allowNegative, negative_balance_limit_cents: Math.round(limit * 100), active, is_default: isDefault };
      if (selected) await api.updateClientGroup(selected.id, payload);
      else await api.createClientGroup({ id: id.trim().toLowerCase(), ...payload });
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить группу клиентов");
    } finally {
      setSaving(false);
    }
  };

  return <section className="white-card product-list-card"><div className="card-heading"><div><h3>Редактор групп клиентов</h3><p>Долг разрешён только для поминутной сессии и ограничен сервером.</p></div><button type="button" className="secondary-button" onClick={() => setSelectedId(null)}>Новая группа</button></div>{groups.map((group) => <div className="settings-row" key={group.id}><div><strong>{group.name}</strong><span>{group.id}{group.allow_negative_balance ? ` · лимит ${(group.negative_balance_limit_cents / 100).toLocaleString("ru-RU")} ₽` : " · без долга"}</span></div><button type="button" className="text-button" onClick={() => setSelectedId(group.id)}>Изменить</button></div>)}<form className="settings-inline-form" onSubmit={(event) => void submit(event)}><div className="form-grid-two"><label>ID группы<input value={id} disabled={Boolean(selected)} onChange={(event) => setId(event.target.value)} placeholder="regular" /></label><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Обычные клиенты" /></label></div><div className="form-grid-two"><label>Лимит долга, ₽<input type="number" min="0" step="0.01" value={limitRubles} onChange={(event) => setLimitRubles(event.target.value)} /></label><label className="settings-checkbox"><input type="checkbox" checked={allowNegative} onChange={(event) => setAllowNegative(event.target.checked)} /> Разрешить отрицательный баланс</label></div><div className="settings-toggle-list"><label><input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} /> Группа по умолчанию</label><label><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Активна</label></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button" disabled={saving}>{saving ? "Сохраняем…" : selected ? "Сохранить группу" : "Создать группу"}</button></form></section>;
}

function NotificationRuleEditor({ api, rules, onSaved }: { api: GameClubApi; rules: BackendNotificationRule[]; onSaved: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = rules.find((rule) => rule.id === selectedId);
  const [threshold, setThreshold] = useState("5");
  const [message, setMessage] = useState("До окончания оплаченного времени осталось 5 минут.");
  const [enabled, setEnabled] = useState(true);
  const [playSound, setPlaySound] = useState(true);
  const [sound, setSound] = useState<"standard" | "custom">("standard");
  const [customSoundPath, setCustomSoundPath] = useState("");
  const [showSystemNotification, setShowSystemNotification] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setThreshold(String(selected?.threshold_minutes ?? 5));
    setMessage(selected?.message ?? "До окончания оплаченного времени осталось 5 минут.");
    setEnabled(selected?.enabled ?? true);
    setPlaySound(selected?.play_sound ?? true);
    setSound(selected?.sound ?? "standard");
    setCustomSoundPath(selected?.custom_sound_path ?? "");
    setShowSystemNotification(selected?.show_system_notification ?? true);
    setError(null);
  }, [selected]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedThreshold = Number(threshold);
    if (!Number.isInteger(parsedThreshold) || parsedThreshold <= 0 || !message.trim() || (sound === "custom" && !/\.(mp3|wav)$/i.test(customSoundPath))) {
      setError("Укажите положительный порог, текст и mp3/wav для собственного звука");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { threshold_minutes: parsedThreshold, enabled, play_sound: playSound, sound, custom_sound_path: sound === "custom" ? customSoundPath.trim() : null, show_system_notification: showSystemNotification, message: message.trim() };
      if (selected) await api.updateNotificationRule(selected.id, payload);
      else await api.createNotificationRule(payload);
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить правило уведомления");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rule: BackendNotificationRule) => {
    if (!window.confirm(`Удалить правило на ${rule.threshold_minutes} минут?`)) return;
    setSaving(true);
    try {
      await api.deleteNotificationRule(rule.id);
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить правило уведомления");
    } finally {
      setSaving(false);
    }
  };

  return <section className="white-card product-list-card"><div className="card-heading"><div><h3>Редактор уведомлений</h3><p>Событие с одним идентификатором не повторяется при reconnect.</p></div><button type="button" className="secondary-button" onClick={() => setSelectedId(null)}>Новое правило</button></div>{rules.map((rule) => <div className="settings-row" key={rule.id}><div><strong>{rule.threshold_minutes} мин — {rule.message}</strong><span>{rule.sound === "custom" ? `Свой звук: ${rule.custom_sound_path}` : "Стандартный звук"}</span></div><span className={rule.enabled ? "active-chip" : "inactive-chip"}>{rule.enabled ? "Включено" : "Выключено"}</span><button type="button" className="text-button" onClick={() => setSelectedId(rule.id)}>Изменить</button><button type="button" className="text-button" onClick={() => void remove(rule)} disabled={saving}>Удалить</button></div>)}<form className="settings-inline-form" onSubmit={(event) => void submit(event)}><div className="form-grid-two"><label>Порог, минут<input type="number" min="1" max="1440" value={threshold} onChange={(event) => setThreshold(event.target.value)} /></label><label>Тип звука<select value={sound} onChange={(event) => setSound(event.target.value as "standard" | "custom")}><option value="standard">Стандартный</option><option value="custom">Собственный mp3/wav</option></select></label></div>{sound === "custom" && <label>Путь к звуку<input value={customSoundPath} onChange={(event) => setCustomSoundPath(event.target.value)} placeholder="C:\\Club\\sounds\\five.wav" /></label>}<label>Текст уведомления<textarea rows={2} value={message} onChange={(event) => setMessage(event.target.value)} /></label><div className="settings-toggle-list"><label><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Включено</label><label><input type="checkbox" checked={playSound} onChange={(event) => setPlaySound(event.target.checked)} /> Воспроизводить звук</label><label><input type="checkbox" checked={showSystemNotification} onChange={(event) => setShowSystemNotification(event.target.checked)} /> Показывать системное уведомление</label></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button" disabled={saving}>{saving ? "Сохраняем…" : selected ? "Сохранить правило" : "Создать правило"}</button></form></section>;
}
