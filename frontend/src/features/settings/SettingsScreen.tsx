import { useEffect, useState } from "react";
import {
  Bell,
  CreditCard,
  Gamepad2,
  Plus,
  Settings,
  Users,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type {
  BackendClientGroup,
  BackendLockdownPolicy,
  BackendNotificationRule,
  BackendPaymentMethod,
  BackendWorkstationGroup,
} from "../../api";
import { themeLabels } from "../../shared/constants";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Workstation } from "../../types";
import { SettingsResourceEditors } from "./SettingsResourceEditors";

export function SettingsView({
  api,
  pcs,
  groups,
  paymentMethods,
  clientGroups = [],
  notificationRules = [],
  error,
  onNewGroup,
  onEditGroup,
  onNewPaymentMethod,
  onEditPaymentMethod,
  onRefresh,
}: {
  api?: GameClubApi;
  pcs: Workstation[];
  groups: BackendWorkstationGroup[];
  paymentMethods: BackendPaymentMethod[];
  clientGroups?: BackendClientGroup[];
  notificationRules?: BackendNotificationRule[];
  error?: string | null;
  onNewGroup?: () => void;
  onEditGroup?: (group: BackendWorkstationGroup) => void;
  onNewPaymentMethod?: () => void;
  onEditPaymentMethod?: (method: BackendPaymentMethod) => void;
  onRefresh?: () => void;
}) {
  const [demoPaymentMethods, setDemoPaymentMethods] = useState<BackendPaymentMethod[]>([
    { id: "balance", key: "balance", name: "Баланс клиента", active: true, sort_order: 0, created_at: "", updated_at: "" },
    { id: "cash", key: "cash", name: "Наличные", active: true, sort_order: 1, created_at: "", updated_at: "" },
    { id: "transfer", key: "transfer", name: "Перевод", active: true, sort_order: 2, created_at: "", updated_at: "" },
  ]);
  const [demoPaymentMethodEditor, setDemoPaymentMethodEditor] = useState<BackendPaymentMethod | null | undefined>(undefined);
  const knownGroupIds = new Set(groups.map((group) => group.id));
  const legacyGroups = pcs.reduce<BackendWorkstationGroup[]>((items, pc) => {
    if (
      !pc.groupId ||
      knownGroupIds.has(pc.groupId) ||
      items.some((group) => group.id === pc.groupId)
    ) {
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
    return (
      <>
        <LiveSettingsLayout
        groups={[
          {
            id: "standard",
            name: "Обычный зал",
            theme: "standard",
            per_minute_price_cents: 100,
            updated_at: null,
          },
          {
            id: "vip",
            name: "VIP-зона",
            theme: "vip",
            per_minute_price_cents: 200,
            updated_at: null,
          },
        ]}
        paymentMethods={demoPaymentMethods}
        clientGroups={[
          {
            id: "debt",
            name: "Долг",
            allow_negative_balance: true,
            negative_balance_limit_cents: 1000000,
            active: true,
            is_default: false,
            updated_at: null,
          },
          {
            id: "regular",
            name: "Обычные клиенты",
            allow_negative_balance: false,
            negative_balance_limit_cents: 0,
            active: true,
            is_default: true,
            updated_at: null,
          },
        ]}
        notificationRules={[]}
        onNewPaymentMethod={() => setDemoPaymentMethodEditor(null)}
        onEditPaymentMethod={setDemoPaymentMethodEditor}
        />
        {demoPaymentMethodEditor !== undefined && (
          <div className="fixed inset-0 z-40 bg-black/50" role="presentation">
            <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-primary/30! bg-base-100/95! text-base-content! shadow-[0_0_32px_rgba(49,217,120,0.12),-14px_0_38px_rgba(0,0,0,0.25)] backdrop-blur-xl" role="dialog" aria-modal="true" aria-label="Редактор способа оплаты">
              <PaymentMethodPanel
                method={demoPaymentMethodEditor ?? undefined}
                onClose={() => setDemoPaymentMethodEditor(undefined)}
                onSaved={() => setDemoPaymentMethodEditor(undefined)}
                onDemoSaved={(savedMethod) => {
                  setDemoPaymentMethods((current) => current.some((item) => item.id === savedMethod.id)
                    ? current.map((item) => item.id === savedMethod.id ? savedMethod : item)
                    : [...current, savedMethod].sort((left, right) => left.sort_order - right.sort_order));
                }}
                onDemoDeleted={(methodId) => {
                  setDemoPaymentMethods((current) => current.filter((item) => item.id !== methodId));
                }}
              />
            </aside>
          </div>
        )}
      </>
    );
  }

  return (
    <LiveSettingsLayout
      api={api}
      groups={visibleGroups}
      paymentMethods={paymentMethods}
      clientGroups={clientGroups}
      notificationRules={notificationRules}
      error={error}
      onNewGroup={onNewGroup}
      onEditGroup={onEditGroup}
      onNewPaymentMethod={onNewPaymentMethod}
      onEditPaymentMethod={onEditPaymentMethod}
      onRefresh={onRefresh}
    />
  );
}

function LiveSettingsLayout({
  api,
  groups,
  paymentMethods,
  clientGroups,
  notificationRules,
  error,
  onNewGroup,
  onEditGroup,
  onNewPaymentMethod,
  onEditPaymentMethod,
  onRefresh,
}: {
  api?: GameClubApi;
  groups: BackendWorkstationGroup[];
  paymentMethods: BackendPaymentMethod[];
  clientGroups: BackendClientGroup[];
  notificationRules: BackendNotificationRule[];
  error?: string | null;
  onNewGroup?: () => void;
  onEditGroup?: (group: BackendWorkstationGroup) => void;
  onNewPaymentMethod?: () => void;
  onEditPaymentMethod?: (method: BackendPaymentMethod) => void;
  onRefresh?: () => void;
}) {
  return (
    <>
      <div
        className="relative mb-3 flex min-h-24 flex-wrap items-center justify-between gap-3 overflow-hidden border-b border-primary/15! bg-base-100/25! p-3"
        style={{
          backgroundImage:
            "linear-gradient(90deg, rgba(7,24,27,.44), rgba(7,24,27,.06)), url(/neon-club-room.png)",
          backgroundPosition: "center 46%",
          backgroundSize: "cover",
          backgroundRepeat: "no-repeat",
        }}
      >
        <div className="relative z-10 flex items-center gap-4">
          <div className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl border border-primary/40! bg-primary/10! text-primary!">
            <Settings size={32} />
          </div>
          <div>
            <p className="mb-0 text-xs text-primary/80!">Конфигурация клуба</p>
            <h1 className="text-3xl font-bold tracking-tight">Настройки</h1>
            <p className="mt-0 text-xs text-base-content/65!">
              В зоне задаются тема, ставка поминутной игры и доступные способы
              оплаты.
            </p>
          </div>
        </div>
        <div className="heading-actions relative z-10 flex flex-wrap items-center gap-2">
          <button
            className="secondary-button btn btn-outline btn-sm"
            onClick={onNewPaymentMethod}
          >
            <Plus size={16} /> Способ оплаты
          </button>
          <button
            className="primary-button btn btn-primary btn-sm"
            onClick={onNewGroup}
          >
            <Plus size={17} /> Добавить группу
          </button>
        </div>
      </div>
      {error && (
        <div
          className="search-hint error mb-4 rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 items-stretch gap-2 lg:grid-cols-2 [&>section]:gap-2 [&>section]:p-3 [&>section:nth-child(3)]:gap-1 [&>section:nth-child(3)]:p-2 [&>section:nth-child(4)]:gap-1 [&>section:nth-child(4)]:p-2 [&>section_.card-heading>span]:size-10 [&>section_.card-heading>span]:rounded-xl [&>section_.card-heading>span_svg]:size-5 [&>section_.card-heading]:gap-3 [&>section_.card-heading_h3]:text-base [&>section_.card-heading_p]:text-xs [&>section_.settings-row]:grid [&>section_.settings-row]:grid-cols-[auto_minmax(0,1fr)_auto_auto] [&>section_.settings-row]:items-center [&>section_.settings-row]:gap-3 [&>section_.settings-row]:py-2 [&>section_.settings-row>span:first-child]:size-10 [&>section_.settings-row>span:first-child]:rounded-xl [&>section_.settings-row>span:first-child_svg]:size-5 [&>section_.settings-row>span:first-child]:shrink-0 [&>section_.settings-row_strong]:text-base [&>section_.settings-row_.text-sm]:text-xs [&>section_.settings-row_.text-sm]:leading-tight">
        <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="card-heading flex items-start justify-between gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Gamepad2 size={20} />
            </span>
            <div className="min-w-0 grow">
              <h3>Группы игровых мест</h3>
              <p>Изменения применяются к игровым местам после сохранения.</p>
            </div>
          </div>
          {groups.length ? (
            groups.map((group) => (
              <div
                className="settings-row grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-primary/15! bg-base-200/40! px-3 py-2 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
                key={group.id}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                  <Gamepad2 size={18} />
                </span>
                <div className="min-w-0 grow flex flex-col gap-1">
                  <strong>{group.name}</strong>
                  <span className="text-sm text-base-content/65!">
                    Поминутка:{" "}
                    {group.per_minute_price_cents > 0
                      ? `${(group.per_minute_price_cents / 100).toLocaleString("ru-RU")} ₽/мин`
                      : "выключена"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="active-chip badge badge-success badge-soft whitespace-nowrap">
                    {themeLabels[group.theme]}
                  </span>
                  <button
                    className="text-button btn btn-ghost btn-sm"
                    onClick={() => onEditGroup?.(group)}
                  >
                    Изменить
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
              Группы ещё не настроены
            </div>
          )}
        </section>
        <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="card-heading flex items-start justify-between gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <CreditCard size={20} />
            </span>
            <div className="min-w-0 grow">
              <h3>Способы оплаты</h3>
              <p>Выберите, чем оператор сможет принять оплату.</p>
            </div>
            <button
              className="secondary-button btn btn-outline btn-sm"
              onClick={onNewPaymentMethod}
            >
              <Plus size={16} /> Добавить
            </button>
          </div>
          {paymentMethods.length ? (
            paymentMethods.map((method) => (
              <div
                className="settings-row grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-primary/15! bg-base-200/40! px-3 py-2 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
                key={method.id}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                  <CreditCard size={18} />
                </span>
                <div className="min-w-0 grow flex flex-col gap-1">
                  <strong>{method.name}</strong>
                  <span className="text-sm text-base-content/65!">
                    {method.sort_order === 0
                      ? "Основной способ"
                      : "Дополнительный способ"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`whitespace-nowrap ${method.active ? "active-chip badge badge-success badge-soft" : "inactive-chip badge badge-neutral badge-soft"}`}
                  >
                    {method.active ? "Включён" : "Выключен"}
                  </span>
                  <button
                    className="text-button btn btn-ghost btn-sm"
                    onClick={() => onEditPaymentMethod?.(method)}
                  >
                    Изменить
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
              Способы оплаты ещё не настроены
            </div>
          )}
        </section>
        <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="card-heading flex items-start justify-between gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Users size={20} />
            </span>
            <div className="min-w-0 grow">
              <h3>Группы клиентов</h3>
              <p>Правила депозита применяются к зарегистрированным клиентам.</p>
            </div>
          </div>
          {clientGroups.length ? (
            clientGroups.map((group) => (
              <div
                className="settings-row grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-xl border border-primary/15! bg-base-200/40! px-3 py-2 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
                key={group.id}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                  <Users size={18} />
                </span>
                <div className="min-w-0 grow flex flex-col gap-1">
                  <strong>{group.name}</strong>
                  <span className="text-sm text-base-content/65!">
                    {group.allow_negative_balance
                      ? `Допустимый долг ${(group.negative_balance_limit_cents / 100).toLocaleString("ru-RU")} ₽ только для поминутной сессии`
                      : "Отрицательный баланс запрещён"}
                  </span>
                </div>
                <span
                  className={
                    group.active
                      ? "active-chip badge badge-success badge-soft"
                      : "inactive-chip badge badge-neutral badge-soft"
                  }
                >
                  {group.is_default
                    ? "По умолчанию"
                    : group.active
                      ? "Включена"
                      : "Выключена"}
                </span>
              </div>
            ))
          ) : (
            <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
              Группы клиентов ещё не настроены
            </div>
          )}
        </section>
        <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="card-heading flex items-start justify-between gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Bell size={20} />
            </span>
            <div className="min-w-0 grow">
              <h3>Уведомления по времени</h3>
              <p>
                Пороговые события готовы для звука и системного уведомления.
              </p>
            </div>
          </div>
          {notificationRules.length ? (
            notificationRules.map((rule) => (
              <div
                className="settings-row grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-xl border border-primary/15! bg-base-200/40! px-3 py-2 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
                key={rule.id}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                  <Bell size={18} />
                </span>
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
              </div>
            ))
          ) : (
            <div className="flex min-h-16 flex-col items-center justify-center gap-2 text-center before:grid before:size-10 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-2xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-3 text-sm text-base-content/60!">
              Правила уведомлений ещё не настроены
            </div>
          )}
        </section>
      </div>
      {api ? (
        <div className="mt-2">
          <SettingsResourceEditors
            api={api}
            clientGroups={clientGroups}
            notificationRules={notificationRules}
            onSaved={() => onRefresh?.()}
          />
        </div>
      ) : (
        <DemoSettingsResourceEditors />
      )}
      <p className="mt-1 text-sm text-base-content/70! settings-note">
        Перевод подтверждается оператором после проверки поступления денег. Все
        операции сохраняются в истории клуба.
      </p>
    </>
  );
}

function DemoSettingsResourceEditors() {
  return (
    <div className="mt-2 grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Users size={18} />
            </span>
            <div>
              <h3 className="font-semibold">Редактор групп клиентов</h3>
              <p className="text-xs text-base-content/60!">
                Долг разрешён только во время поминутной игры и ограничен указанной суммой.
              </p>
            </div>
          </div>
          <button className="btn btn-outline btn-sm" type="button">Новая группа</button>
        </div>
        <div className="grid gap-1 rounded-xl border border-primary/15! bg-base-200/45 p-2 text-sm shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <div className="flex items-center justify-between rounded-lg border border-primary/10! bg-base-100/35 px-2 py-1.5">
            <span><strong>Долг</strong> <small className="text-base-content/55">· dolq · лимит 10 000 ₽</small></span>
            <button className="btn btn-ghost btn-xs" type="button">Изменить</button>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-primary/10! bg-base-100/35 px-2 py-1.5">
            <span><strong>Обычные клиенты</strong> <small className="text-base-content/55">· regular · без долга</small></span>
            <button className="btn btn-ghost btn-xs" type="button">Изменить</button>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-2 border-t border-primary/15! pt-2 md:grid-cols-2">
          <label className="form-control text-xs">ID группы<input className="input input-sm mt-1" value="regular" readOnly /></label>
          <label className="form-control text-xs">Название<input className="input input-sm mt-1" value="Обычные клиенты" readOnly /></label>
          <label className="form-control text-xs">Лимит долга, ₽<input className="input input-sm mt-1" value="0" readOnly /></label>
          <label className="flex items-end gap-2 pb-1 text-xs"><input className="toggle toggle-primary toggle-sm" type="checkbox" /> Разрешить отрицательный баланс</label>
        </div>
        <div className="flex flex-wrap gap-3 rounded-lg border border-primary/15! bg-base-200/60 p-2 text-xs">
          <label className="flex items-center gap-2"><input className="toggle toggle-primary toggle-sm" type="checkbox" /> Группа по умолчанию</label>
          <label className="flex items-center gap-2"><input className="toggle toggle-primary toggle-sm" type="checkbox" defaultChecked /> Активна</label>
        </div>
        <button className="btn btn-primary btn-sm w-full" type="button">Сохранить группу</button>
      </section>
      <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Bell size={18} />
            </span>
            <div>
              <h3 className="font-semibold">Редактор уведомлений</h3>
              <p className="text-xs text-base-content/60!">Уведомление не дублируется после восстановления связи.</p>
            </div>
          </div>
          <button className="btn btn-outline btn-sm" type="button">Новое правило</button>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <label className="form-control text-xs">Порог, минут<input className="input input-sm mt-1" value="5" readOnly /></label>
          <label className="form-control text-xs">Тип звука<select className="select select-sm mt-1" defaultValue="standard"><option value="standard">Стандартный</option></select></label>
        </div>
        <label className="form-control text-xs">Текст уведомления<textarea className="textarea textarea-sm mt-1" rows={2} value="До окончания оплаченного времени осталось 5 минут." readOnly /></label>
        <div className="grid gap-1 rounded-lg border border-primary/15! bg-base-200/60 p-2 text-xs">
          <label className="flex items-center gap-2"><input className="toggle toggle-primary toggle-sm" type="checkbox" defaultChecked /> Включено</label>
          <label className="flex items-center gap-2"><input className="toggle toggle-primary toggle-sm" type="checkbox" defaultChecked /> Воспроизводить звук</label>
          <label className="flex items-center gap-2"><input className="toggle toggle-primary toggle-sm" type="checkbox" defaultChecked /> Показывать системное уведомление</label>
        </div>
        <button className="btn btn-primary btn-sm w-full" type="button">Создать правило</button>
      </section>
    </div>
  );
}

export function GroupSettingsPanel({
  api,
  group,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  group?: BackendWorkstationGroup;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [groupId, setGroupId] = useState(group?.id ?? "");
  const [name, setName] = useState(group?.name ?? "");
  const [theme, setTheme] = useState<BackendWorkstationGroup["theme"]>(
    group?.theme ?? "standard",
  );
  const [perMinutePrice, setPerMinutePrice] = useState(
    group ? String(group.per_minute_price_cents / 100) : "0",
  );
  const [managerPassword, setManagerPassword] = useState("");
  const [deploymentMode, setDeploymentMode] = useState<
    BackendLockdownPolicy["deployment_mode"]
  >(group?.lockdown_policy?.deployment_mode ?? "app_gate");
  const [shellEnabled, setShellEnabled] = useState(
    group?.lockdown_policy?.shell_enabled ?? true,
  );
  const [userSelfLoginEnabled, setUserSelfLoginEnabled] = useState(
    group?.lockdown_policy?.user_self_login_enabled ?? true,
  );
  const [lockAfterSession, setLockAfterSession] = useState(
    group?.lockdown_policy?.lock_after_session ?? true,
  );
  const [restartAfterSession, setRestartAfterSession] = useState(
    group?.lockdown_policy?.restart_after_session ?? true,
  );
  const [blockExternalStorage, setBlockExternalStorage] = useState(
    group?.lockdown_policy?.block_external_storage ?? false,
  );
  const [disableStartMenu, setDisableStartMenu] = useState(
    group?.lockdown_policy?.disable_start_menu ?? false,
  );
  const [disableDesktopSwitching, setDisableDesktopSwitching] = useState(
    group?.lockdown_policy?.disable_desktop_switching ?? false,
  );
  const [hiddenDrives, setHiddenDrives] = useState(
    (group?.lockdown_policy?.hidden_drives ?? []).join(", "),
  );
  const [blockedWindowRules, setBlockedWindowRules] = useState(
    (group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"),
  );
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
    setUserSelfLoginEnabled(
      group?.lockdown_policy?.user_self_login_enabled ?? true,
    );
    setLockAfterSession(group?.lockdown_policy?.lock_after_session ?? true);
    setRestartAfterSession(
      group?.lockdown_policy?.restart_after_session ?? true,
    );
    setBlockExternalStorage(
      group?.lockdown_policy?.block_external_storage ?? false,
    );
    setDisableStartMenu(group?.lockdown_policy?.disable_start_menu ?? false);
    setDisableDesktopSwitching(
      group?.lockdown_policy?.disable_desktop_switching ?? false,
    );
    setHiddenDrives((group?.lockdown_policy?.hidden_drives ?? []).join(", "));
    setBlockedWindowRules(
      (group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"),
    );
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
        hidden_drives: hiddenDrives
          .split(",")
          .map((item) => item.trim().toUpperCase())
          .filter(Boolean),
        block_external_storage: blockExternalStorage,
        disable_start_menu: disableStartMenu,
        disable_desktop_switching: disableDesktopSwitching,
        blocked_window_rules: blockedWindowRules
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        allowed_application_ids:
          group?.lockdown_policy?.allowed_application_ids ?? [],
        version: (group?.lockdown_policy?.version ?? 0) + 1,
      };
      await api.setWorkstationGroupLockdownPolicy(groupId, policy);
      if (managerPassword) {
        await api.setWorkstationGroupManagerPassword(groupId, managerPassword);
      }
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить группу",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Настройки зон"
        subtitle={group ? "Изменение группы" : "Новая группа ПК"}
        onClose={onClose}
      />
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Идентификатор группы
          <input
            className="input input-sm"
            value={groupId}
            onChange={(event) => setGroupId(event.target.value)}
            placeholder="vip"
            autoFocus
            disabled={Boolean(group)}
          />
        </label>
        <label>
          Название группы
          <input
            className="input input-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="VIP-зона"
          />
        </label>
        <label>
          Цена поминутки, ₽
          <input
            className="input input-sm"
            type="number"
            min="0"
            step="0.01"
            value={perMinutePrice}
            onChange={(event) => setPerMinutePrice(event.target.value)}
            placeholder="0"
          />
          <span className="field-hint text-xs text-base-content/60!">
            0 — поминутное списание отключено для этой зоны.
          </span>
        </label>
        <label>
          Тема Windows-клиента
          <select
            className="select select-sm"
            value={theme}
            onChange={(event) =>
              setTheme(event.target.value as BackendWorkstationGroup["theme"])
            }
          >
            {Object.entries(themeLabels).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Режим блокировки Windows
          <select
            className="select select-sm"
            value={deploymentMode}
            onChange={(event) =>
              setDeploymentMode(
                event.target.value as BackendLockdownPolicy["deployment_mode"],
              )
            }
          >
            <option value="app_gate">Только access-gate приложения</option>
            <option value="assigned_access">Assigned Access</option>
            <option value="shell_launcher">Shell Launcher</option>
          </select>
        </label>
        <div className="settings-toggle-list flex flex-col gap-2 rounded-lg border border-primary/15! bg-base-200/55! p-3 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={shellEnabled}
              onChange={(event) => setShellEnabled(event.target.checked)}
            />{" "}
            Запускать клиент HUBSHELL
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={userSelfLoginEnabled}
              onChange={(event) =>
                setUserSelfLoginEnabled(event.target.checked)
              }
            />{" "}
            Разрешить вход пользователя
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={lockAfterSession}
              onChange={(event) => setLockAfterSession(event.target.checked)}
            />{" "}
            Блокировать после сессии
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={restartAfterSession}
              onChange={(event) => setRestartAfterSession(event.target.checked)}
            />{" "}
            Перезапускать ПК после сессии
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={blockExternalStorage}
              onChange={(event) =>
                setBlockExternalStorage(event.target.checked)
              }
            />{" "}
            Запретить внешние накопители
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={disableStartMenu}
              onChange={(event) => setDisableStartMenu(event.target.checked)}
            />{" "}
            Ограничить меню «Пуск»
          </label>
          <label>
            <input
              className="toggle toggle-primary toggle-sm"
              type="checkbox"
              checked={disableDesktopSwitching}
              onChange={(event) =>
                setDisableDesktopSwitching(event.target.checked)
              }
            />{" "}
            Запретить смену рабочих столов
          </label>
        </div>
        <label>
          Скрытые диски
          <input
            className="input input-sm"
            value={hiddenDrives}
            onChange={(event) => setHiddenDrives(event.target.value)}
            placeholder="C:, D:"
          />
        </label>
        <label>
          Блокируемые окна/классы
          <textarea
            className="textarea textarea-sm"
            value={blockedWindowRules}
            onChange={(event) => setBlockedWindowRules(event.target.value)}
            placeholder="CabinetWClass\n*cmd*"
            rows={3}
          />
        </label>
        <label>
          Пароль менеджера Win-клиента
          <input
            className="input input-sm"
            type="password"
            value={managerPassword}
            onChange={(event) => setManagerPassword(event.target.value)}
            placeholder={
              group ? "Оставьте пустым без изменений" : "Минимум 8 символов"
            }
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
          />
        </label>
        <p className="mt-1 text-sm text-base-content/65!">
          Эти параметры задают режим работы игровых мест. Пароль обслуживания
          нужен только для действий администратора на Windows-клиенте.
        </p>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting}
        >
          {submitting ? "Сохраняем..." : "Сохранить группу"}
        </button>
        <p className="mt-1 text-sm text-base-content/65!">
          После сохранения игровые места получат новые параметры при следующем
          подключении.
        </p>
      </form>
    </div>
  );
}

export function PaymentMethodPanel({
  api,
  method,
  onClose,
  onSaved,
  onDemoSaved,
  onDemoDeleted,
}: {
  api?: GameClubApi;
  method?: BackendPaymentMethod;
  onClose: () => void;
  onSaved: () => void;
  onDemoSaved?: (method: BackendPaymentMethod) => void;
  onDemoDeleted?: (methodId: string) => void;
}) {
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
    if (
      !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(key.trim().toLowerCase()) ||
      !name.trim() ||
      !Number.isInteger(parsedOrder) ||
      parsedOrder < 0
    ) {
      setError(
        "Укажите ключ (латиница, цифры, _ или -), название и порядок сортировки",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        key: key.trim().toLowerCase(),
        name: name.trim(),
        active,
        sort_order: parsedOrder,
      };
      if (!api) {
        onDemoSaved?.({
          id: method?.id ?? `demo-payment-${Date.now()}`,
          ...payload,
          created_at: method?.created_at ?? "",
          updated_at: new Date().toISOString(),
        });
        onSaved();
      } else {
        if (method) {
          await api.updatePaymentMethod(method.id, payload);
        } else {
          await api.createPaymentMethod(payload);
        }
        onSaved();
      }
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить способ оплаты",
      );
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
      if (!api) {
        onDemoDeleted?.(method.id);
        onSaved();
        return;
      }
      await api.deletePaymentMethod(method.id);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось удалить способ оплаты",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Способ оплаты"
        subtitle={method ? "Изменение способа оплаты" : "Новый способ оплаты"}
        onClose={onClose}
      />
      <form
        className="booking-form flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          Системный ключ
          <input
            className="input input-sm"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            placeholder="transfer"
            autoFocus
          />
        </label>
        <label>
          Название в интерфейсе
          <input
            className="input input-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Перевод"
          />
        </label>
        <label>
          Порядок отображения
          <input
            className="input input-sm"
            type="number"
            min="0"
            step="1"
            value={sortOrder}
            onChange={(event) => setSortOrder(event.target.value)}
          />
        </label>
        <label
          className={`settings-checkbox flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${active ? "border-primary/35! bg-primary/10!" : "border-primary/15! bg-base-200/55!"}`}
        >
          <input
            className="toggle toggle-primary toggle-sm"
            type="checkbox"
            aria-label="Показывать как активный способ"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
          />{" "}
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <strong className="block">Показывать как активный способ</strong>
              <span
                className={`badge badge-sm ${active ? "badge-success badge-soft" : "badge-neutral badge-outline"}`}
              >
                {active ? "Включён" : "Выключен"}
              </span>
            </span>
            <small className="text-base-content/60!">
              Способ будет доступен оператору при оформлении продажи.
            </small>
          </span>
        </label>
        <p className="mt-1 text-sm text-base-content/65!">
          Перевод подтверждает оператор после проверки поступления денег. Баланс
          и наличные проводят оплату сразу по выбранному способу.
        </p>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          type="submit"
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting}
        >
          {submitting
            ? "Сохраняем..."
            : method
              ? "Сохранить изменения"
              : "Добавить способ оплаты"}
        </button>
        {method && (
          <button
            type="button"
            className="danger-button btn btn-error btn-outline btn-block w-full"
            onClick={() => void remove()}
            disabled={submitting}
          >
            Удалить способ оплаты
          </button>
        )}
      </form>
    </div>
  );
}
