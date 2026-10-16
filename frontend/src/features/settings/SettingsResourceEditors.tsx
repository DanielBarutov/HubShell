import { useEffect, useState } from "react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendClientGroup, BackendNotificationRule } from "../../api";

export function SettingsResourceEditors({
  api,
  clientGroups,
  notificationRules,
  onSaved,
}: {
  api?: GameClubApi;
  clientGroups: BackendClientGroup[];
  notificationRules: BackendNotificationRule[];
  onSaved: () => void;
}) {
  if (!api) return null;
  return (
    <div className="settings-resource-editors grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ClientGroupEditor api={api} groups={clientGroups} onSaved={onSaved} />
      <NotificationRuleEditor
        api={api}
        rules={notificationRules}
        onSaved={onSaved}
      />
    </div>
  );
}

function ClientGroupEditor({
  api,
  groups,
  onSaved,
}: {
  api: GameClubApi;
  groups: BackendClientGroup[];
  onSaved: () => void;
}) {
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
    setLimitRubles(
      selected ? String(selected.negative_balance_limit_cents / 100) : "0",
    );
    setActive(selected?.active ?? true);
    setIsDefault(selected?.is_default ?? false);
    setError(null);
  }, [selected]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const limit = Number(limitRubles.replace(",", "."));
    if (
      !id.trim() ||
      !name.trim() ||
      !Number.isFinite(limit) ||
      limit < 0 ||
      (!allowNegative && limit !== 0)
    ) {
      setError("Укажите группу, название и корректный лимит долга");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: name.trim(),
        allow_negative_balance: allowNegative,
        negative_balance_limit_cents: Math.round(limit * 100),
        active,
        is_default: isDefault,
      };
      if (selected) await api.updateClientGroup(selected.id, payload);
      else
        await api.createClientGroup({
          id: id.trim().toLowerCase(),
          ...payload,
        });
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить группу клиентов",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card gap-4 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
      <div className="card-heading flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Редактор групп клиентов</h3>
          <p className="mt-1 text-sm text-base-content/65">
            Долг разрешён только во время поминутной игры и ограничен указанной
            суммой.
          </p>
        </div>
        <button
          type="button"
          className="secondary-button btn btn-outline btn-sm"
          onClick={() => setSelectedId(null)}
        >
          Новая группа
        </button>
      </div>
      {groups.map((group) => (
        <div
          className="settings-row flex flex-wrap items-center gap-3 border-t border-primary/15! py-3"
          key={group.id}
        >
          <div className="min-w-0 grow flex flex-col gap-1">
            <strong>{group.name}</strong>
            <span className="text-sm text-base-content/65!">
              {group.id}
              {group.allow_negative_balance
                ? ` · лимит ${(group.negative_balance_limit_cents / 100).toLocaleString("ru-RU")} ₽`
                : " · без долга"}
            </span>
          </div>
          <button
            type="button"
            className="text-button btn btn-ghost btn-sm"
            onClick={() => setSelectedId(group.id)}
          >
            Изменить
          </button>
        </div>
      ))}
      <form
        className="settings-inline-form mt-4 flex flex-col gap-3 border-t border-primary/15! pt-4"
        onSubmit={(event) => void submit(event)}
      >
        <div className="form-grid-two grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            ID группы
            <input
              className="input input-sm w-full"
              value={id}
              disabled={Boolean(selected)}
              onChange={(event) => setId(event.target.value)}
              placeholder="regular"
            />
          </label>
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            Название
            <input
              className="input input-sm w-full"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Обычные клиенты"
            />
          </label>
        </div>
        <div className="form-grid-two grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            Лимит долга, ₽
            <input
              className="input input-sm w-full"
              type="number"
              min="0"
              step="0.01"
              value={limitRubles}
              onChange={(event) => setLimitRubles(event.target.value)}
            />
          </label>
          <label className="settings-checkbox flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={allowNegative}
              onChange={(event) => setAllowNegative(event.target.checked)}
            />{" "}
            Разрешить отрицательный баланс
          </label>
        </div>
        <div className="settings-toggle-list flex flex-col gap-2 rounded-lg border border-primary/15! bg-base-200/55! p-3 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={isDefault}
              onChange={(event) => setIsDefault(event.target.checked)}
            />{" "}
            Группа по умолчанию
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
            />{" "}
            Активна
          </label>
        </div>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-sm"
          disabled={saving}
        >
          {saving
            ? "Сохраняем…"
            : selected
              ? "Сохранить группу"
              : "Создать группу"}
        </button>
      </form>
    </section>
  );
}

function NotificationRuleEditor({
  api,
  rules,
  onSaved,
}: {
  api: GameClubApi;
  rules: BackendNotificationRule[];
  onSaved: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = rules.find((rule) => rule.id === selectedId);
  const [threshold, setThreshold] = useState("5");
  const [message, setMessage] = useState(
    "До окончания оплаченного времени осталось 5 минут.",
  );
  const [enabled, setEnabled] = useState(true);
  const [playSound, setPlaySound] = useState(true);
  const [sound, setSound] = useState<"standard" | "custom">("standard");
  const [customSoundPath, setCustomSoundPath] = useState("");
  const [showSystemNotification, setShowSystemNotification] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setThreshold(String(selected?.threshold_minutes ?? 5));
    setMessage(
      selected?.message ?? "До окончания оплаченного времени осталось 5 минут.",
    );
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
    if (
      !Number.isInteger(parsedThreshold) ||
      parsedThreshold <= 0 ||
      !message.trim() ||
      (sound === "custom" && !/\.(mp3|wav)$/i.test(customSoundPath))
    ) {
      setError(
        "Укажите положительный порог, текст и mp3/wav для собственного звука",
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        threshold_minutes: parsedThreshold,
        enabled,
        play_sound: playSound,
        sound,
        custom_sound_path: sound === "custom" ? customSoundPath.trim() : null,
        show_system_notification: showSystemNotification,
        message: message.trim(),
      };
      if (selected) await api.updateNotificationRule(selected.id, payload);
      else await api.createNotificationRule(payload);
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить правило уведомления",
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rule: BackendNotificationRule) => {
    if (!window.confirm(`Удалить правило на ${rule.threshold_minutes} минут?`))
      return;
    setSaving(true);
    try {
      await api.deleteNotificationRule(rule.id);
      setSelectedId(null);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось удалить правило уведомления",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card gap-4 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
      <div className="card-heading flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Редактор уведомлений</h3>
          <p className="mt-1 text-sm text-base-content/65">Уведомление не дублируется после восстановления связи.</p>
        </div>
        <button
          type="button"
          className="secondary-button btn btn-outline btn-sm"
          onClick={() => setSelectedId(null)}
        >
          Новое правило
        </button>
      </div>
      {rules.map((rule) => (
        <div
          className="settings-row flex flex-wrap items-center gap-3 border-t border-primary/15! py-3"
          key={rule.id}
        >
          <div className="min-w-0 grow flex flex-col gap-1">
            <strong>
              {rule.threshold_minutes} мин — {rule.message}
            </strong>
            <span className="text-sm text-base-content/65!">
              {rule.sound === "custom"
                ? `Свой звук: ${rule.custom_sound_path}`
                : "Стандартный звук"}
            </span>
          </div>
          <span
            className={
              rule.enabled
                ? "active-chip badge badge-success badge-soft"
                : "inactive-chip badge badge-neutral badge-soft"
            }
          >
            {rule.enabled ? "Включено" : "Выключено"}
          </span>
          <button
            type="button"
            className="text-button btn btn-ghost btn-sm"
            onClick={() => setSelectedId(rule.id)}
          >
            Изменить
          </button>
          <button
            type="button"
            className="text-button btn btn-ghost btn-sm"
            onClick={() => void remove(rule)}
            disabled={saving}
          >
            Удалить
          </button>
        </div>
      ))}
      <form
        className="settings-inline-form mt-4 flex flex-col gap-3 border-t border-primary/15! pt-4"
        onSubmit={(event) => void submit(event)}
      >
        <div className="form-grid-two grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            Порог, минут
            <input
              className="input input-sm w-full"
              type="number"
              min="1"
              max="1440"
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
            />
          </label>
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            Тип звука
            <select
              className="select select-sm w-full"
              value={sound}
              onChange={(event) =>
                setSound(event.target.value as "standard" | "custom")
              }
            >
              <option value="standard">Стандартный</option>
              <option value="custom">Собственный mp3/wav</option>
            </select>
          </label>
        </div>
        {sound === "custom" && (
          <label className="flex min-w-0 flex-col gap-2 text-sm">
            Путь к звуку
            <input
              className="input input-sm w-full"
              value={customSoundPath}
              onChange={(event) => setCustomSoundPath(event.target.value)}
              placeholder="C:\\Club\\sounds\\five.wav"
            />
          </label>
        )}
        <label className="flex min-w-0 flex-col gap-2 text-sm">
          Текст уведомления
          <textarea
            className="textarea textarea-sm w-full"
            rows={2}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
        </label>
        <div className="settings-toggle-list flex flex-col gap-2 rounded-lg border border-primary/15! bg-base-200/55! p-3 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />{" "}
            Включено
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={playSound}
              onChange={(event) => setPlaySound(event.target.checked)}
            />{" "}
            Воспроизводить звук
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={showSystemNotification}
              onChange={(event) =>
                setShowSystemNotification(event.target.checked)
              }
            />{" "}
            Показывать системное уведомление
          </label>
        </div>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-sm"
          disabled={saving}
        >
          {saving
            ? "Сохраняем…"
            : selected
              ? "Сохранить правило"
              : "Создать правило"}
        </button>
      </form>
    </section>
  );
}
