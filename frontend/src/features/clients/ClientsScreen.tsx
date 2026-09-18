import { useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, ChevronDown, ChevronRight, Edit3, Plus, Search, ShieldCheck, Sparkles } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendBalanceOperation, BackendClientAnalytics, BackendClientGroup } from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client } from "../../types";

export function ClientsView({
  search,
  setSearch,
  onDeposit,
  onNewClient,
  onClient,
  clients: clientList,
  api,
}: {
  search: string;
  setSearch: (value: string) => void;
  onDeposit: () => void;
  onNewClient?: () => void;
  onClient: (client: Client) => void;
  clients: Client[];
  api?: GameClubApi;
}) {
  const normalized = search.toLowerCase().trim();
  const searchField = getSearchField(normalized);
  const canSearch = searchField !== null;
  const [liveResults, setLiveResults] = useState<Client[]>(clientList);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      setLiveResults(clientList);
      return undefined;
    }
    if (!searchField) {
      setLiveResults(search.trim() ? [] : clientList);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(normalized, searchField);
        if (active) {
          setLiveResults(found.map(toUiClient));
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
  }, [api, clientList, normalized, searchField]);

  const results = api
    ? liveResults
    : canSearch
      ? clientList.filter((client) => client.nickname.toLowerCase().includes(normalized) || client.phone.replace(/\D/g, "").includes(normalized.replace(/\D/g, "")))
      : clientList;
  return <><div className="page-heading"><div><p className="eyebrow">{api ? `${clientList.length} клиентов онлайн` : "Демонстрация"}</p><h1>Клиенты</h1><p className="subheading">Поиск, баланс и история операций клуба.</p></div><div className="heading-actions">{onNewClient && <button className="secondary-button" onClick={onNewClient}><Plus size={15} /> Новый клиент</button>}<button className="primary-button" onClick={onDeposit}><Plus size={17} /> Пополнить депозит</button></div></div><div className="search-row"><div className="search-box"><Search size={17} /><input aria-label="Поиск клиента" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти по нику или телефону..." /></div><button className="secondary-button">Фильтры <ChevronDown size={15} /></button></div>{search && !canSearch && <div className="search-hint">Введите минимум 3 символа ника или 4 цифры номера</div>}{searchError && <div className="search-hint error" role="alert">{searchError}</div>}<div className="table-card"><div className="table-head"><span>Клиент</span><span>Категория</span><span>Баланс</span><span>Бонусы</span><span>Последний визит</span><span /></div>{results.map((client) => <div className="table-row" key={client.id}><div className="client-cell"><div className="client-avatar">{client.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{client.nickname}</strong><span>{formatRussianPhone(client.phone)}</span></div></div><span className="category-chip">{client.category}</span><strong>{client.balance.toLocaleString("ru-RU")} ₽</strong><span className="bonus-value">+{client.bonus} ₽</span><span className="muted">{api ? "—" : "Сегодня, 11:24"}</span><button className="icon-button small" aria-label={`Открыть клиента ${client.nickname}`} onClick={() => onClient(client)}><ChevronRight size={16} /></button></div>)}</div></>;
}

export function ClientPanel({ client, clientGroups, api, onClose, onSaved, onDeposit, onBonusDeposit }: { client: Client; clientGroups: BackendClientGroup[]; api?: GameClubApi; onClose: () => void; onSaved: () => void; onDeposit: () => void; onBonusDeposit: () => void }) {
  const defaultGroupId = clientGroups.find((group) => group.is_default)?.id ?? "";
  const selectableGroups = clientGroups.filter((group) => group.active || group.id === client.clientGroupId);
  const currentGroup = clientGroups.find((group) => group.id === client.clientGroupId);
  const [operations, setOperations] = useState<BackendBalanceOperation[]>([]);
  const [analytics, setAnalytics] = useState<BackendClientAnalytics | null>(null);
  const [discountRules, setDiscountRules] = useState<Awaited<ReturnType<GameClubApi["listDiscountRules"]>>>([]);
  const [editing, setEditing] = useState(false);
  const [nickname, setNickname] = useState(client.nickname);
  const [phone, setPhone] = useState(formatRussianPhone(client.phone));
  const [category, setCategory] = useState(client.category === "Без скидки" ? "" : client.category);
  const [clientGroupId, setClientGroupId] = useState(client.clientGroupId ?? defaultGroupId);
  const [error, setError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(api));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setClientGroupId(client.clientGroupId ?? defaultGroupId);
  }, [client.clientGroupId, defaultGroupId]);

  useEffect(() => {
    if (!api) {
      setLoading(false);
      return undefined;
    }
    let active = true;
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - 29);
    end.setDate(end.getDate() + 1);
    void Promise.all([
      api.listClientOperations(client.id),
      api.listDiscountRules(),
      api.getClientAnalytics(client.id, start.toISOString(), end.toISOString(), 6),
    ]).then(([items, rules, clientAnalytics]) => {
      if (active) {
        setOperations(items);
        setDiscountRules(rules);
        setAnalytics(clientAnalytics);
        setLoading(false);
      }
    }).catch((requestError) => {
      if (active) {
        setLoading(false);
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить данные клиента");
      }
    });
    return () => { active = false; };
  }, [api, client.id]);

  const categories = Array.from(new Set(discountRules.map((rule) => rule.category)));
  if (category && !categories.includes(category)) categories.unshift(category);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!api) return;
    if (nickname.trim().length < 3) {
      setError("Ник должен содержать минимум 3 символа");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const selectedGroup = clientGroups.find((group) => group.id === clientGroupId);
      await api.updateClient(client.id, { nickname: nickname.trim(), phone: phone.trim() || undefined, discount_category: category || undefined, client_group_id: selectedGroup?.active ? selectedGroup.id : undefined });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить клиента");
    } finally {
      setSaving(false);
    }
  };

  const resetPassword = async () => {
    if (!api || !window.confirm(`Сбросить пароль клиента «${client.nickname}»?`)) return;
    setSaving(true);
    setError(null);
    setPasswordMessage(null);
    try {
      await api.resetClientPassword(client.id);
      setPasswordMessage("Пароль сброшен. При следующем входе клиент сможет войти без пароля и задаст новый.");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сбросить пароль");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!api || !window.confirm(`Удалить клиента «${client.nickname}» из активного списка?`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteClient(client.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить клиента");
      setSaving(false);
    }
  };

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  return <div className="panel-inner"><PanelHeader title={client.nickname} subtitle="Карточка клиента" onClose={onClose} /><div className="panel-pc-hero client-panel-hero"><div className="client-avatar large-client-avatar">{client.nickname.slice(0, 2).toUpperCase()}</div><div><span className="category-chip">{client.category}</span>{currentGroup && <span className="category-chip">{currentGroup.name}</span>}<h2>{formatRussianPhone(client.phone)}</h2><p>Профиль клиента и операции</p></div></div><div className="client-action-grid"><button className="secondary-button" onClick={() => setEditing((value) => !value)}><Edit3 size={14} /> {editing ? "Отменить" : "Редактировать"}</button><button className="secondary-button" onClick={() => void resetPassword()} disabled={!api || saving}><ShieldCheck size={14} /> Сбросить пароль</button></div>{passwordMessage && <div className="form-success" role="status">{passwordMessage}</div>}{editing && <form className="booking-form client-edit-form" onSubmit={(event) => void save(event)}><label>Ник<input value={nickname} onChange={(event) => setNickname(event.target.value)} /></label><label>Телефон<input type="tel" inputMode="tel" value={phone} onChange={(event) => setPhone(formatRussianPhone(event.target.value))} placeholder="+7 (999) 000-00-00" /></label><label>Категория скидки<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Без скидки</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select></label><label>Группа клиента<select aria-label="Группа клиента" value={clientGroupId} onChange={(event) => setClientGroupId(event.target.value)} disabled={!selectableGroups.length}><option value="" disabled>Выберите группу</option>{selectableGroups.map((group) => <option value={group.id} key={group.id}>{group.name}{group.is_default ? " · по умолчанию" : ""}{group.active ? "" : " · отключена"}</option>)}</select></label><button className="primary-button wide" disabled={saving || !selectableGroups.length}>{saving ? "Сохраняем..." : "Сохранить клиента"}</button></form>}<div className="panel-section client-balance-section"><div className="balance-highlight"><div><span>Основной баланс</span><strong>{client.balance.toLocaleString("ru-RU")} ₽</strong></div><div><span>Бонусный баланс</span><strong className="bonus-value">{client.bonus.toLocaleString("ru-RU")} ₽</strong></div></div><div className="client-action-grid"><button className="primary-button" onClick={onDeposit}><Plus size={14} /> Пополнить баланс</button><button className="secondary-button" onClick={onBonusDeposit}><Sparkles size={14} /> Начислить бонусы</button></div></div>{analytics && <div className="panel-section client-analytics-section"><div className="operation-heading"><h3>Статистика клиента</h3><span>Последние 30 дней</span></div><div className="client-analytics-grid"><div><strong>{analytics.played_hours.toLocaleString("ru-RU")} ч</strong><span>Игровое время</span></div><div><strong>{analytics.session_count}</strong><span>Сессий</span></div><div><strong>{money(analytics.total_spend_cents)}</strong><span>Всего потрачено</span></div><div><strong>{analytics.average_session_minutes.toLocaleString("ru-RU")} мин</strong><span>Средняя сессия</span></div><div><strong>{money(analytics.product_spend_cents)}</strong><span>Товары</span></div><div><strong>{analytics.product_units}</strong><span>Товаров куплено</span></div></div><div className="client-analytics-meta"><span>Первый визит: {analytics.first_session_at ? new Date(analytics.first_session_at).toLocaleDateString("ru-RU") : "нет данных"}</span><span>Последний визит: {analytics.last_session_at ? new Date(analytics.last_session_at).toLocaleDateString("ru-RU") : "нет данных"}</span></div>{analytics.favorite_products.length > 0 && <div className="client-favorites"><span>Любимые товары</span>{analytics.favorite_products.map((item) => <span className="category-chip" key={item.product_id}>{item.product_name} · {item.units} шт.</span>)}</div>}</div>}{loading && <div className="timeline-empty">Загружаем операции и статистику…</div>}{error && <div className="form-error" role="alert">{error}</div>}<div className="panel-section operation-section"><div className="operation-heading"><h3>История операций</h3><span>{api ? "Последние 20" : "Пример"}</span></div>{!loading && !api && <div className="timeline-empty">Операции появятся после пополнения или списания.</div>}{!loading && api && !operations.length && <div className="timeline-empty">Операций пока нет</div>}{operations.map((operation) => <div className="operation-row" key={operation.id}><div className={`operation-icon ${operation.amount_cents >= 0 ? "income" : "expense"}`}>{operation.amount_cents >= 0 ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}</div><div><strong>{operation.reason || (operation.operation_type === "top_up" ? "Пополнение" : "Списание")}</strong><span>{new Date(operation.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}{operation.bonus_amount ? ` · бонус +${operation.bonus_amount} ₽` : ""}</span></div><b className={operation.amount_cents >= 0 ? "income-text" : "expense-text"}>{operation.amount_cents >= 0 ? "+" : ""}{(operation.amount_cents / 100).toLocaleString("ru-RU")} ₽</b></div>)}</div><button className="danger-button client-delete-button" onClick={() => void remove()} disabled={!api || saving}>Удалить клиента <ChevronRight size={15} /></button></div>;
}

export function NewClientPanel({ api, clientGroups, onClose, onSaved }: { api: GameClubApi; clientGroups: BackendClientGroup[]; onClose: () => void; onSaved: () => void }) {
  const defaultGroupId = clientGroups.find((group) => group.is_default && group.active)?.id ?? "";
  const selectableGroups = clientGroups.filter((group) => group.active);
  const [nickname, setNickname] = useState("");
  const [phone, setPhone] = useState("");
  const [category, setCategory] = useState("");
  const [clientGroupId, setClientGroupId] = useState(defaultGroupId);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (nickname.trim().length < 3) {
      setError("Ник должен содержать минимум 3 символа");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createClient({
        nickname: nickname.trim(),
        phone: phone.trim() || undefined,
        discount_category: category.trim() || undefined,
        client_group_id: clientGroupId || undefined,
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать клиента");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Новый клиент" subtitle="Профиль клиента" onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Ник<input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder="night_walker" autoFocus /></label><label>Телефон<input type="tel" inputMode="tel" value={phone} onChange={(event) => setPhone(formatRussianPhone(event.target.value))} placeholder="+7 (999) 000-00-00" /></label><label>Категория скидки<input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="student" /></label><label>Группа клиента<select aria-label="Группа клиента" value={clientGroupId} onChange={(event) => setClientGroupId(event.target.value)} disabled={!selectableGroups.length}><option value="">Группа по умолчанию</option>{selectableGroups.map((group) => <option value={group.id} key={group.id}>{group.name}{group.is_default ? " · по умолчанию" : ""}</option>)}</select></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !selectableGroups.length}>{submitting ? "Создаём..." : "Создать клиента"}</button><p className="subheading">Телефон сохраняется в едином формате +7XXXXXXXXXX.</p></form></div>;
}
