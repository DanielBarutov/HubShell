import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendLockdownPolicy, BackendPaymentMethod, BackendWorkstationGroup } from "../../api";
import { themeLabels } from "../../shared/constants";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Workstation } from "../../types";

export function SettingsView({ api, pcs, refreshKey, onNewGroup, onEditGroup, onNewPaymentMethod, onEditPaymentMethod }: { api?: GameClubApi; pcs: Workstation[]; refreshKey: number; onNewGroup?: () => void; onEditGroup?: (group: BackendWorkstationGroup) => void; onNewPaymentMethod?: () => void; onEditPaymentMethod?: (method: BackendPaymentMethod) => void }) {
  const [groups, setGroups] = useState<BackendWorkstationGroup[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<BackendPaymentMethod[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      return undefined;
    }
    let active = true;
    Promise.all([api.listWorkstationGroups(), api.listPaymentMethods()]).then(([groupItems, methodItems]) => {
      if (active) {
        setGroups(groupItems);
        setPaymentMethods(methodItems);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить настройки");
      }
    });
    return () => {
      active = false;
    };
  }, [api, refreshKey]);

  const knownGroupIds = new Set(groups.map((group) => group.id));
  const legacyGroups = pcs.reduce<BackendWorkstationGroup[]>((items, pc) => {
    if (!pc.groupId || knownGroupIds.has(pc.groupId) || items.some((group) => group.id === pc.groupId)) {
      return items;
    }
    items.push({
      id: pc.groupId,
      name: pc.group,
      theme: pc.groupId.toLowerCase().includes("vip") ? "vip" : "standard",
      per_minute_price_cents: 0,
      updated_at: null,
    });
    return items;
  }, []);
  const visibleGroups = [...groups, ...legacyGroups];

  if (!api) {
    return <><div className="page-heading"><div><p className="eyebrow">Конфигурация клуба</p><h1>Настройки</h1><p className="subheading">Группы игровых мест, оформление клиента и способы оплаты.</p></div></div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Темы групп</h3><p>Настройки, которые увидят игровые места.</p></div></div><div className="settings-row"><div><strong>VIP-зона</strong><span>Тема по умолчанию для демонстрации</span></div><span className="active-chip">VIP-зона</span></div><div className="settings-row"><div><strong>Обычный зал</strong><span>Тема по умолчанию для демонстрации</span></div><span className="active-chip">Обычный зал</span></div></div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Способы оплаты</h3><p>Варианты, доступные оператору при оформлении продажи.</p></div></div><div className="settings-row"><div><strong>Баланс клиента</strong><span>Оплата с депозита</span></div><span className="active-chip">Включён</span></div><div className="settings-row"><div><strong>Наличные</strong><span>Оплата в кассу</span></div><span className="active-chip">Включён</span></div></div></>;
  }

  return <><div className="page-heading"><div><p className="eyebrow">Конфигурация клуба</p><h1>Настройки</h1><p className="subheading">В зоне задаются тема, ставка поминутной игры и доступные способы оплаты.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onNewPaymentMethod}><Plus size={16} /> Способ оплаты</button><button className="primary-button" onClick={onNewGroup}><Plus size={17} /> Добавить группу</button></div></div>{error && <div className="search-hint error" role="alert">{error}</div>}<div className="white-card product-list-card"><div className="card-heading"><div><h3>Группы игровых мест</h3><p>Изменения применяются к игровым местам после сохранения.</p></div></div>{visibleGroups.length ? visibleGroups.map((group) => <div className="settings-row" key={group.id}><div><strong>{group.name}</strong><span>Поминутка: {group.per_minute_price_cents > 0 ? `${(group.per_minute_price_cents / 100).toLocaleString("ru-RU")} ₽/мин` : "выключена"}</span></div><span className="active-chip">{themeLabels[group.theme]}</span><button className="text-button" onClick={() => onEditGroup?.(group)}>Изменить</button></div>) : <div className="timeline-empty">Группы ещё не настроены</div>}</div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Способы оплаты</h3><p>Выберите, чем оператор сможет принять оплату.</p></div><button className="secondary-button" onClick={onNewPaymentMethod}><Plus size={16} /> Добавить</button></div>{paymentMethods.length ? paymentMethods.map((method) => <div className="settings-row payment-method-row" key={method.id}><div><strong>{method.name}</strong><span>{method.sort_order === 0 ? "Основной способ" : "Дополнительный способ"}</span></div><span className={method.active ? "active-chip" : "inactive-chip"}>{method.active ? "Включён" : "Выключен"}</span><button className="text-button" onClick={() => onEditPaymentMethod?.(method)}>Изменить</button></div>) : <div className="timeline-empty">Способы оплаты ещё не настроены</div>}</div><p className="subheading settings-note">Перевод подтверждается оператором после проверки поступления денег. Все операции сохраняются в истории клуба.</p></>;
}

export function GroupSettingsPanel({ api, group, onClose, onSaved }: { api: GameClubApi; group?: BackendWorkstationGroup; onClose: () => void; onSaved: () => void }) {
  const [groupId, setGroupId] = useState(group?.id ?? "");
  const [name, setName] = useState(group?.name ?? "");
  const [theme, setTheme] = useState<BackendWorkstationGroup["theme"]>(group?.theme ?? "standard");
  const [perMinutePrice, setPerMinutePrice] = useState(group ? String(group.per_minute_price_cents / 100) : "0");
  const [managerPassword, setManagerPassword] = useState("");
  const [deploymentMode, setDeploymentMode] = useState<BackendLockdownPolicy["deployment_mode"]>(group?.lockdown_policy?.deployment_mode ?? "app_gate");
  const [shellEnabled, setShellEnabled] = useState(group?.lockdown_policy?.shell_enabled ?? true);
  const [userSelfLoginEnabled, setUserSelfLoginEnabled] = useState(group?.lockdown_policy?.user_self_login_enabled ?? true);
  const [lockAfterSession, setLockAfterSession] = useState(group?.lockdown_policy?.lock_after_session ?? true);
  const [restartAfterSession, setRestartAfterSession] = useState(group?.lockdown_policy?.restart_after_session ?? true);
  const [blockExternalStorage, setBlockExternalStorage] = useState(group?.lockdown_policy?.block_external_storage ?? false);
  const [disableStartMenu, setDisableStartMenu] = useState(group?.lockdown_policy?.disable_start_menu ?? false);
  const [disableDesktopSwitching, setDisableDesktopSwitching] = useState(group?.lockdown_policy?.disable_desktop_switching ?? false);
  const [hiddenDrives, setHiddenDrives] = useState((group?.lockdown_policy?.hidden_drives ?? []).join(", "));
  const [blockedWindowRules, setBlockedWindowRules] = useState((group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setGroupId(group?.id ?? "");
    setName(group?.name ?? "");
    setTheme(group?.theme ?? "standard");
    setPerMinutePrice(group ? String(group.per_minute_price_cents / 100) : "0");
    setManagerPassword("");
    setDeploymentMode(group?.lockdown_policy?.deployment_mode ?? "app_gate");
    setShellEnabled(group?.lockdown_policy?.shell_enabled ?? true);
    setUserSelfLoginEnabled(group?.lockdown_policy?.user_self_login_enabled ?? true);
    setLockAfterSession(group?.lockdown_policy?.lock_after_session ?? true);
    setRestartAfterSession(group?.lockdown_policy?.restart_after_session ?? true);
    setBlockExternalStorage(group?.lockdown_policy?.block_external_storage ?? false);
    setDisableStartMenu(group?.lockdown_policy?.disable_start_menu ?? false);
    setDisableDesktopSwitching(group?.lockdown_policy?.disable_desktop_switching ?? false);
    setHiddenDrives((group?.lockdown_policy?.hidden_drives ?? []).join(", "));
    setBlockedWindowRules((group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"));
    setError(null);
  }, [group]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!groupId.trim() || !name.trim()) {
      setError("Укажите идентификатор и название группы");
      return;
    }
    const perMinutePriceRubles = Number(perMinutePrice.replace(",", "."));
    if (!Number.isFinite(perMinutePriceRubles) || perMinutePriceRubles < 0) {
      setError("Укажите корректную цену поминутки или 0, чтобы отключить её");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.saveWorkstationGroup(groupId, {
        name: name.trim(),
        theme,
        per_minute_price_cents: Math.round(perMinutePriceRubles * 100),
      });
      const policy: BackendLockdownPolicy = {
        deployment_mode: deploymentMode,
        shell_enabled: shellEnabled,
        user_self_login_enabled: userSelfLoginEnabled,
        lock_after_session: lockAfterSession,
        restart_after_session: restartAfterSession,
        hidden_drives: hiddenDrives.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
        block_external_storage: blockExternalStorage,
        disable_start_menu: disableStartMenu,
        disable_desktop_switching: disableDesktopSwitching,
        blocked_window_rules: blockedWindowRules.split("\n").map((item) => item.trim()).filter(Boolean),
        allowed_application_ids: group?.lockdown_policy?.allowed_application_ids ?? [],
        version: (group?.lockdown_policy?.version ?? 0) + 1,
      };
      await api.setWorkstationGroupLockdownPolicy(groupId, policy);
      if (managerPassword) {
        await api.setWorkstationGroupManagerPassword(groupId, managerPassword);
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить группу");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner">
    <PanelHeader title="Настройки зон" subtitle={group ? "Изменение группы" : "Новая группа ПК"} onClose={onClose} />
    <form className="booking-form" onSubmit={submit}>
      <label>Идентификатор группы<input value={groupId} onChange={(event) => setGroupId(event.target.value)} placeholder="vip" autoFocus disabled={Boolean(group)} /></label>
      <label>Название группы<input value={name} onChange={(event) => setName(event.target.value)} placeholder="VIP-зона" /></label>
      <label>Цена поминутки, ₽<input type="number" min="0" step="0.01" value={perMinutePrice} onChange={(event) => setPerMinutePrice(event.target.value)} placeholder="0" /><span className="field-hint">0 — поминутное списание отключено для этой зоны.</span></label>
      <label>Тема Windows-клиента<select value={theme} onChange={(event) => setTheme(event.target.value as BackendWorkstationGroup["theme"])}>{Object.entries(themeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>Режим блокировки Windows<select value={deploymentMode} onChange={(event) => setDeploymentMode(event.target.value as BackendLockdownPolicy["deployment_mode"])}><option value="app_gate">Только access-gate приложения</option><option value="assigned_access">Assigned Access</option><option value="shell_launcher">Shell Launcher</option></select></label>
      <div className="settings-toggle-list">
        <label><input type="checkbox" checked={shellEnabled} onChange={(event) => setShellEnabled(event.target.checked)} /> Запускать клиент HUBSHELL</label>
        <label><input type="checkbox" checked={userSelfLoginEnabled} onChange={(event) => setUserSelfLoginEnabled(event.target.checked)} /> Разрешить вход пользователя</label>
        <label><input type="checkbox" checked={lockAfterSession} onChange={(event) => setLockAfterSession(event.target.checked)} /> Блокировать после сессии</label>
        <label><input type="checkbox" checked={restartAfterSession} onChange={(event) => setRestartAfterSession(event.target.checked)} /> Перезапускать ПК после сессии</label>
        <label><input type="checkbox" checked={blockExternalStorage} onChange={(event) => setBlockExternalStorage(event.target.checked)} /> Запретить внешние накопители</label>
        <label><input type="checkbox" checked={disableStartMenu} onChange={(event) => setDisableStartMenu(event.target.checked)} /> Ограничить Start Menu</label>
        <label><input type="checkbox" checked={disableDesktopSwitching} onChange={(event) => setDisableDesktopSwitching(event.target.checked)} /> Запретить смену рабочих столов</label>
      </div>
      <label>Скрытые диски<input value={hiddenDrives} onChange={(event) => setHiddenDrives(event.target.value)} placeholder="C:, D:" /></label>
      <label>Блокируемые окна/классы<textarea value={blockedWindowRules} onChange={(event) => setBlockedWindowRules(event.target.value)} placeholder="CabinetWClass\n*cmd*" rows={3} /></label>
      <label>Пароль менеджера Win-клиента<input type="password" value={managerPassword} onChange={(event) => setManagerPassword(event.target.value)} placeholder={group ? "Оставьте пустым без изменений" : "Минимум 8 символов"} autoComplete="new-password" minLength={8} maxLength={128} /></label>
      <p className="subheading">Эти параметры задают режим работы игровых мест. Пароль обслуживания нужен только для действий администратора на Windows-клиенте.</p>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Сохранить группу"}</button>
      <p className="subheading">После сохранения игровые места получат новые параметры при следующем подключении.</p>
    </form>
  </div>;
}

export function PaymentMethodPanel({ api, method, onClose, onSaved }: { api: GameClubApi; method?: BackendPaymentMethod; onClose: () => void; onSaved: () => void }) {
  const [key, setKey] = useState(method?.key ?? "");
  const [name, setName] = useState(method?.name ?? "");
  const [active, setActive] = useState(method?.active ?? true);
  const [sortOrder, setSortOrder] = useState(String(method?.sort_order ?? 0));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setKey(method?.key ?? "");
    setName(method?.name ?? "");
    setActive(method?.active ?? true);
    setSortOrder(String(method?.sort_order ?? 0));
    setError(null);
  }, [method]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedOrder = Number(sortOrder);
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(key.trim().toLowerCase()) || !name.trim() || !Number.isInteger(parsedOrder) || parsedOrder < 0) {
      setError("Укажите ключ (латиница, цифры, _ или -), название и порядок сортировки");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { key: key.trim().toLowerCase(), name: name.trim(), active, sort_order: parsedOrder };
      if (method) {
        await api.updatePaymentMethod(method.id, payload);
      } else {
        await api.createPaymentMethod(payload);
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить способ оплаты");
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!method || !window.confirm(`Удалить способ оплаты «${method.name}»?`)) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.deletePaymentMethod(method.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить способ оплаты");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Способ оплаты" subtitle={method ? "Изменение способа оплаты" : "Новый способ оплаты"} onClose={onClose} /><form className="booking-form" onSubmit={(event) => void submit(event)}><label>Системный ключ<input value={key} onChange={(event) => setKey(event.target.value)} placeholder="transfer" autoFocus /></label><label>Название в интерфейсе<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Перевод" /></label><label>Порядок отображения<input type="number" min="0" step="1" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} /></label><label className="settings-checkbox"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Показывать как активный способ</label><p className="subheading">Ключ transfer — ручной подтверждённый перевод без кассовой смены. Ключи balance и cash проводят баланс и наличные.</p>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : method ? "Сохранить изменения" : "Добавить способ оплаты"}</button>{method && <button type="button" className="danger-button" onClick={() => void remove()} disabled={submitting}>Удалить способ оплаты</button>}</form></div>;
}
