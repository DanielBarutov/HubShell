import { useEffect, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Edit3,
  KeyRound,
  MoreHorizontal,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Users,
  WalletCards,
  Crown,
  Activity,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type {
  BackendBalanceOperation,
  BackendClientAnalytics,
  BackendClientGroup,
} from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { MetricDecoration } from "../../shared/components/MetricCard";
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
          setSearchError(
            error instanceof ApiError
              ? error.message
              : "Не удалось выполнить поиск",
          );
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
      ? clientList.filter(
          (client) =>
            client.nickname.toLowerCase().includes(normalized) ||
            client.phone
              .replace(/\D/g, "")
              .includes(normalized.replace(/\D/g, "")),
        )
      : clientList;
  const totalBalance = clientList.reduce(
    (sum, client) => sum + client.balance,
    0,
  );
  const metricCards = [
    [
      "Всего клиентов",
      api ? clientList.length.toLocaleString("ru-RU") : "1 342",
      api ? "зарегистрировано" : "+12 за неделю",
      Users,
    ],
    [
      "Онлайн сейчас",
      api ? clientList.length.toLocaleString("ru-RU") : "10",
      api ? "активных профиля" : "из 1 342 клиентов",
      Activity,
    ],
    [
      "С депозитом",
      api ? `${totalBalance.toLocaleString("ru-RU")} ₽` : "318",
      api ? "общий баланс" : "24% от всех",
      WalletCards,
    ],
  ] as const;
  return (
    <>
      <div className="relative mb-3 mt-7 flex min-h-28 flex-wrap items-start justify-between gap-3">
        <div className="relative z-10">
          <div>
            <p className="mb-1 text-sm text-primary/80!">
              {api
                ? `${clientList.length} клиентов онлайн`
                : "10 клиентов онлайн"}
            </p>
            <h1 className="text-3xl font-bold tracking-tight">Клиенты</h1>
            <p className="mt-1 text-xs text-base-content/65!">
              Поиск, баланс и история операций клуба.
            </p>
          </div>
        </div>
        <div className="heading-actions relative z-10 flex flex-wrap items-center gap-2">
          {(onNewClient || !api) && (
            <button
              className="secondary-button btn btn-outline"
              onClick={onNewClient}
            >
              <Plus size={15} /> Новый клиент
            </button>
          )}
          <button
            className="primary-button btn btn-primary bg-primary! text-primary-content!"
            onClick={onDeposit}
          >
            <Plus size={17} /> Пополнить депозит
          </button>
        </div>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {metricCards.map(([label, value, note, Icon]) => (
          <div
            className="card relative flex-row! min-h-16! items-center gap-2 overflow-hidden border border-primary/25! bg-base-100/85! p-2! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_20px_rgba(49,217,120,0.1)] backdrop-blur-md"
            key={label}
          >
            <span
              className={`grid size-9 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary"}`}
            >
              <Icon size={20} />
            </span>
            <div className="relative z-10 min-w-0 grow">
              <span className="block whitespace-normal text-sm text-base-content/70!">
                {label}
              </span>
              <strong className="block text-xl font-bold text-base-content!">
                {value}
              </strong>
              <small className="block whitespace-normal text-[11px] text-base-content/55!">
                {note}
              </small>
            </div>
            <span className="pointer-events-none relative z-10 hidden shrink-0 opacity-70 xl:block">
              <MetricDecoration title={label} icon={null} variant="clients" />
            </span>
          </div>
        ))}
      </div>
      <div className="search-row mb-3 flex flex-wrap items-center gap-2">
        <label className="search-box input flex min-w-56 grow items-center gap-2 border-primary/20! bg-base-100/55! text-base-content! shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <Search size={17} />
          <input
            className="grow bg-transparent outline-none"
            aria-label="Поиск клиента"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Найти по нику или телефону..."
          />
        </label>
        <button className="secondary-button btn btn-outline">
          <SlidersHorizontal size={15} /> Фильтры <ChevronDown size={15} />
        </button>
      </div>
      {search && !canSearch && (
        <div className="search-hint rounded-lg border border-primary/20! bg-base-100/55! p-3 text-sm text-base-content/70!">
          Введите минимум 3 символа ника или 4 цифры номера
        </div>
      )}
      {searchError && (
        <div
          className="search-hint error mb-3 rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {searchError}
        </div>
      )}
      <div className="overflow-x-auto rounded-xl border border-primary/20! bg-base-100/75! shadow-[0_0_24px_rgba(49,217,120,0.08)] backdrop-blur-md">
        <div className="grid min-w-[760px] grid-cols-[minmax(220px,1.6fr)_minmax(120px,1fr)_minmax(100px,1fr)_minmax(100px,1fr)_minmax(140px,auto)_auto] gap-3 border-b border-primary/20! bg-base-200/70! px-4 py-2 text-xs text-base-content/60!">
          <span>Клиент</span>
          <span>Категория</span>
          <span>Баланс</span>
          <span>Бонусы</span>
          <span>Последний визит</span>
          <span />
        </div>
        {results.map((client, index) => (
          <div
            className={`grid min-w-[760px] grid-cols-[minmax(220px,0.80fr)_minmax(100px,0.9fr)_minmax(100px,0.5fr)_minmax(100px,1fr)_minmax(140px,auto)_auto] items-center gap-3 border-b px-4 py-2 last:border-b-0 ${index === 0 ? "border-primary/50! bg-primary/10!" : "border-primary/10!"}`}
            key={client.id}
          >
            <div className="flex min-w-0 items-center gap-3">
              <span className="size-1 shrink-0 rounded-full bg-success shadow-[0_0_10px_rgba(156,255,115,0.8)]" />
              <div className="client-avatar grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary! text-sm font-bold text-primary-content!">
                {client.nickname.slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0 sm:flex sm:items-center sm:gap-4">
                <strong className="block truncate text-[12px]">
                  {client.nickname}
                </strong>
                <span className="block shrink-0 text-[10px] text-base-content/60!">
                  {formatRussianPhone(client.phone)}
                </span>
              </div>
            </div>
            <span className="flex min-w-0 items-center justify-self-center gap-1">
              <span
                className={`badge text-[10px] gap-1 ${client.category.includes("vip") ? "border border-warning/45! bg-warning/20! text-warning!" : client.category.includes("Без категории") ? "badge-success badge-soft" : "badge-neutral bg-base-300! text-base-content/80!"}`}
              >
                {client.category.includes("vip") && <Crown size={12} />}
                {client.category}
              </span>
            </span>
            <strong className="text-sm justify-self-center">
              {client.balance.toLocaleString("ru-RU", {
                minimumFractionDigits: Number.isInteger(client.balance) ? 0 : 2,
                maximumFractionDigits: 2,
              })}{" "}
              ₽
            </strong>
            <span className="badge text-sm badge-soft badge-success gap-1 justify-self-center">
              <Sparkles size={12} />+{client.bonus} ₽
            </span>
            <span className="flex min-w-0 items-center gap-2 text-sm text-base-content/60!">
              <i
                className={`size-2 shrink-0 rounded-full ${api ? "bg-base-content/35" : "bg-success shadow-[0_0_8px_rgba(156,255,115,0.7)]"}`}
              />
              <span className="min-w-0 truncate">
                <strong className="block text-sm font-medium text-base-content!">
                  {api ? "—" : "Сегодня, 11:24"}
                </strong>
                {!api && (
                  <small className="block text-xs text-success!">
                    Сейчас в клубе
                  </small>
                )}
              </span>
            </span>
            <div className="flex items-center justify-end gap-1">
              <button
                className="icon-button small btn btn-ghost btn-circle btn-sm"
                aria-label={`Открыть клиента ${client.nickname}`}
                onClick={() => onClient(client)}
              >
                <ChevronRight size={16} />
              </button>
              <button
                className="btn btn-ghost btn-square btn-sm text-base-content/60!"
                aria-label={`Дополнительные действия для ${client.nickname}`}
                onClick={() => onClient(client)}
              >
                <MoreHorizontal size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

export function ClientPanel({
  client,
  clientGroups,
  api,
  onClose,
  onSaved,
  onDeposit,
  onBonusDeposit,
}: {
  client: Client;
  clientGroups: BackendClientGroup[];
  api?: GameClubApi;
  onClose: () => void;
  onSaved: () => void;
  onDeposit: () => void;
  onBonusDeposit: () => void;
}) {
  const defaultGroupId =
    clientGroups.find((group) => group.is_default)?.id ?? "";
  const selectableGroups = clientGroups.filter(
    (group) => group.active || group.id === client.clientGroupId,
  );
  const currentGroup = clientGroups.find(
    (group) => group.id === client.clientGroupId,
  );
  const [operations, setOperations] = useState<BackendBalanceOperation[]>([]);
  const [analytics, setAnalytics] = useState<BackendClientAnalytics | null>(
    null,
  );
  const [discountRules, setDiscountRules] = useState<
    Awaited<ReturnType<GameClubApi["listDiscountRules"]>>
  >([]);
  const [editing, setEditing] = useState(false);
  const [nickname, setNickname] = useState(client.nickname);
  const [phone, setPhone] = useState(formatRussianPhone(client.phone));
  const [category, setCategory] = useState(
    client.category === "Без скидки" ? "" : client.category,
  );
  const [clientGroupId, setClientGroupId] = useState(
    client.clientGroupId ?? defaultGroupId,
  );
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
      api.getClientAnalytics(
        client.id,
        start.toISOString(),
        end.toISOString(),
        6,
      ),
    ])
      .then(([items, rules, clientAnalytics]) => {
        if (active) {
          setOperations(items);
          setDiscountRules(rules);
          setAnalytics(clientAnalytics);
          setLoading(false);
        }
      })
      .catch((requestError) => {
        if (active) {
          setLoading(false);
          setError(
            requestError instanceof ApiError
              ? requestError.message
              : "Не удалось загрузить данные клиента",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [api, client.id]);

  const categories = Array.from(
    new Set(discountRules.map((rule) => rule.category)),
  );
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
      const selectedGroup = clientGroups.find(
        (group) => group.id === clientGroupId,
      );
      await api.updateClient(client.id, {
        nickname: nickname.trim(),
        phone: phone.trim() || undefined,
        discount_category: category || undefined,
        client_group_id: selectedGroup?.active ? selectedGroup.id : undefined,
      });
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить клиента",
      );
    } finally {
      setSaving(false);
    }
  };

  const resetPassword = async () => {
    if (
      !api ||
      !window.confirm(`Сбросить пароль клиента «${client.nickname}»?`)
    )
      return;
    setSaving(true);
    setError(null);
    setPasswordMessage(null);
    try {
      await api.resetClientPassword(client.id);
      setPasswordMessage(
        "Пароль сброшен. При следующем входе клиент сможет войти без пароля и задаст новый.",
      );
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сбросить пароль",
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (
      !api ||
      !window.confirm(
        `Удалить клиента «${client.nickname}» из активного списка?`,
      )
    )
      return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteClient(client.id);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось удалить клиента",
      );
      setSaving(false);
    }
  };

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title={client.nickname}
        subtitle="Карточка клиента"
        onClose={onClose}
      />
      <div className="panel-pc-hero client-panel-hero flex items-center gap-3 rounded-xl border border-primary/20! bg-base-200/70! p-4 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
        <div className="client-avatar large-client-avatar grid size-15 place-items-center rounded-full border border-primary/40 bg-primary/25 text-sm font-bold text-primary">
          {client.nickname.slice(0, 2).toUpperCase()}
        </div>
        <div>
          <span className="badge badge-soft badge-neutral bg-base-300! text-base-content/80!">
            {client.category}
          </span>
          {currentGroup && (
            <span className="badge badge-soft badge-neutral bg-base-300! text-base-content/80!">
              {currentGroup.name}
            </span>
          )}
          <h2 className="text-xl font-bold text-base-content!">
            {formatRussianPhone(client.phone)}
          </h2>
          <p className="text-xs text-base-content/40!">
            Профиль клиента и операции
          </p>
        </div>
      </div>
      <div className="client-action-grid grid grid-cols-2 gap-2">
        <button
          className="secondary-button btn btn-outline"
          onClick={() => setEditing((value) => !value)}
        >
          <Edit3 size={14} /> {editing ? "Отменить" : "Редактировать"}
        </button>
        <button
          className="secondary-button btn btn-outline"
          onClick={() => void resetPassword()}
          disabled={!api || saving}
        >
          <KeyRound size={14} /> Сбросить пароль
        </button>
      </div>
      {passwordMessage && (
        <div
          className="form-success rounded-lg border border-success/40! bg-success/10! p-3 text-sm text-success-content!"
          role="status"
        >
          {passwordMessage}
        </div>
      )}
      {editing && (
        <form
          className="booking-form client-edit-form flex flex-col gap-3"
          onSubmit={(event) => void save(event)}
        >
          <label>
            Ник
            <input
              className="input input-sm"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
            />
          </label>
          <label>
            Телефон
            <input
              className="input input-sm"
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={(event) =>
                setPhone(formatRussianPhone(event.target.value))
              }
              placeholder="+7 (999) 000-00-00"
            />
          </label>
          <label>
            Категория скидки
            <select
              className="select select-sm"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">Без скидки</option>
              {categories.map((item) => (
                <option value={item} key={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Группа клиента
            <select
              className="select select-sm"
              aria-label="Группа клиента"
              value={clientGroupId}
              onChange={(event) => setClientGroupId(event.target.value)}
              disabled={!selectableGroups.length}
            >
              <option value="" disabled>
                Выберите группу
              </option>
              {selectableGroups.map((group) => (
                <option value={group.id} key={group.id}>
                  {group.name}
                  {group.is_default ? " · по умолчанию" : ""}
                  {group.active ? "" : " · отключена"}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-button wide btn btn-primary w-full bg-primary! text-primary-content!"
            disabled={saving || !selectableGroups.length}
          >
            {saving ? "Сохраняем..." : "Сохранить клиента"}
          </button>
        </form>
      )}
      <div className="panel-section client-balance-section rounded-xl border border-primary/15! bg-base-200/40! p-4">
        <div className="rounded-xl bg-primary/15! p-3 text-sm!">
          <div>
            <span>Основной баланс</span>
            <strong className="badge badge-outline badge-md font-bold ml-5">
              {client.balance.toLocaleString("ru-RU")} ₽
            </strong>
          </div>
          <div className="mt-2">
            <span>Бонусный баланс</span>
            <strong className="badge badge-outline badge-md font-bold ml-5">
              {client.bonus.toLocaleString("ru-RU")} ₽
            </strong>
          </div>
        </div>
        <div className="client-action-grid grid grid-cols-2 gap-2 mt-4">
          <button
            className="primary-button btn btn-primary bg-primary! text-primary-content! text-xs"
            onClick={onDeposit}
          >
            <Plus size={14} /> Пополнить баланс
          </button>
          <button
            className="secondary-button btn btn-outline text-xs"
            onClick={onBonusDeposit}
          >
            <Sparkles size={14} /> Начислить бонусы
          </button>
        </div>
      </div>
      {analytics && (
        <div className="panel-section client-analytics-section rounded-xl border border-primary/15! bg-base-200/40! p-4">
          <div className="operation-heading mb-2 flex items-center justify-between gap-3">
            <h3>Статистика клиента</h3>
            <span className="text-xs text-base-content/40!">
              Последние 30 дней
            </span>
          </div>
          <div className="client-analytics-grid grid grid-cols-2 gap-2">
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>
                {analytics.played_hours.toLocaleString("ru-RU")} ч
              </strong>
              <span className="text-sm text-base-content/40!">
                Игровое время
              </span>
            </div>
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>{analytics.session_count}</strong>
              <span className="text-sm text-base-content/40!">Сессий</span>
            </div>
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>{money(analytics.total_spend_cents)}</strong>
              <span className="text-sm text-base-content/40!">
                Всего потрачено
              </span>
            </div>
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>
                {analytics.average_session_minutes.toLocaleString("ru-RU")} мин
              </strong>
              <span className="text-sm text-base-content/40!">
                Средняя сессия
              </span>
            </div>
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>{money(analytics.product_spend_cents)}</strong>
              <span className="text-sm text-base-content/40!">Товары</span>
            </div>
            <div className="flex flex-col items-center border border-primary/20! rounded-lg p-2 gap-1">
              <strong>{analytics.product_units}</strong>
              <span className="text-sm text-base-content/40!">
                Товаров куплено
              </span>
            </div>
          </div>
          <div className="client-analytics-meta mt-2 flex flex-wrap gap-2 text-xs text-base-content/60!">
            <span>
              Первый визит:{" "}
              {analytics.first_session_at
                ? new Date(analytics.first_session_at).toLocaleDateString(
                    "ru-RU",
                  )
                : "нет данных"}
            </span>
            <span>
              Последний визит:{" "}
              {analytics.last_session_at
                ? new Date(analytics.last_session_at).toLocaleDateString(
                    "ru-RU",
                  )
                : "нет данных"}
            </span>
          </div>
          {analytics.favorite_products.length > 0 && (
            <div className="client-favorites mt-2 flex flex-wrap items-center gap-2">
              <span>Любимые товары</span>
              {analytics.favorite_products.map((item) => (
                <span
                  className="badge badge-soft badge-neutral bg-base-300! text-base-content/80!"
                  key={item.product_id}
                >
                  {item.product_name} · {item.units} шт.
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {loading && (
        <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
          Загружаем операции и статистику…
        </div>
      )}
      {error && (
        <div
          className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {error}
        </div>
      )}
      <div className="panel-section operation-section rounded-xl border border-primary/15! bg-base-200/40! p-4">
        <div className="operation-heading mb-2 flex items-center justify-between gap-3">
          <h3>История операций</h3>
          <span className="text-xs text-base-content/40!">
            {api ? "Последние 20" : "Пример"}
          </span>
        </div>
        {!loading && !api && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
            Операции появятся после пополнения или списания.
          </div>
        )}
        {!loading && api && !operations.length && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
            Операций пока нет
          </div>
        )}
        {operations.map((operation) => (
          <div
            className="operation-row flex items-center gap-3 border-t border-primary/10! py-2 text-xs"
            key={operation.id}
          >
            <div
              className={`grid size-7 place-items-center rounded-lg ${operation.amount_cents >= 0 ? "bg-primary/15! text-primary!" : "bg-error/15! text-error!"}`}
            >
              {operation.amount_cents >= 0 ? (
                <ArrowDownLeft size={14} />
              ) : (
                <ArrowUpRight size={14} />
              )}
            </div>
            <div>
              <strong>
                {operation.reason ||
                  (operation.operation_type === "top_up"
                    ? "Пополнение"
                    : "Списание")}
              </strong>
              <span>
                {new Date(operation.created_at).toLocaleString("ru-RU", {
                  day: "2-digit",
                  month: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                {operation.bonus_amount
                  ? ` · бонус +${operation.bonus_amount} ₽`
                  : ""}
              </span>
            </div>
            <b
              className={
                operation.amount_cents >= 0
                  ? "whitespace-nowrap text-primary!"
                  : "whitespace-nowrap text-error!"
              }
            >
              {operation.amount_cents >= 0 ? "+" : ""}
              {(operation.amount_cents / 100).toLocaleString("ru-RU")} ₽
            </b>
          </div>
        ))}
      </div>
      <button
        className="danger-button client-delete-button btn btn-error btn-outline w-full"
        onClick={() => void remove()}
        disabled={!api || saving}
      >
        Удалить клиента <ChevronRight size={15} />
      </button>
    </div>
  );
}

export function NewClientPanel({
  api,
  clientGroups,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  clientGroups: BackendClientGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const defaultGroupId =
    clientGroups.find((group) => group.is_default && group.active)?.id ?? "";
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
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось создать клиента",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Новый клиент"
        subtitle="Профиль клиента"
        onClose={onClose}
      />
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Ник
          <input
            className="input input-sm"
            value={nickname}
            onChange={(event) => setNickname(event.target.value)}
            placeholder="night_walker"
            autoFocus
          />
        </label>
        <label>
          Телефон
          <input
            className="input input-sm"
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={(event) =>
              setPhone(formatRussianPhone(event.target.value))
            }
            placeholder="+7 (999) 000-00-00"
          />
        </label>
        <label>
          Категория скидки
          <input
            className="input input-sm"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="student"
          />
        </label>
        <label>
          Группа клиента
          <select
            className="select select-sm"
            aria-label="Группа клиента"
            value={clientGroupId}
            onChange={(event) => setClientGroupId(event.target.value)}
            disabled={!selectableGroups.length}
          >
            <option value="">Группа по умолчанию</option>
            {selectableGroups.map((group) => (
              <option value={group.id} key={group.id}>
                {group.name}
                {group.is_default ? " · по умолчанию" : ""}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button wide btn btn-primary w-full bg-primary! text-primary-content!"
          disabled={submitting || !selectableGroups.length}
        >
          {submitting ? "Создаём..." : "Создать клиента"}
        </button>
        <p className="mt-1 text-sm text-base-content/70! text-sm text-base-content/65!">
          Телефон сохраняется в едином формате +7XXXXXXXXXX.
        </p>
      </form>
    </div>
  );
}
