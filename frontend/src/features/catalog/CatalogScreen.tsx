import { useEffect, useState } from "react";
import {
  ChevronRight,
  Clock3,
  Edit3,
  Layers3,
  MoreHorizontal,
  PackageOpen,
  Percent,
  Plus,
  ShoppingCart,
  Settings,
  X,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type {
  BackendDiscountRule,
  BackendProduct,
  BackendProductCategory,
  BackendTariff,
  BackendWorkstationGroup,
} from "../../api";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { localDateTimeValue } from "../../shared/formatters";

const tariffAccentColors = [
  "rgba(49,217,120,.28)",
  "rgba(49,168,164,.24)",
  "rgba(160,95,255,.26)",
  "rgba(245,194,78,.24)",
  "rgba(49,217,120,.22)",
  "rgba(255,145,70,.22)",
];
const tariffScenes = [
  "/tariff-green.png",
  "/tariff-blue.png",
  "/tariff-purple.png",
  "/tariff-purple-alt.png",
  "/tariff-green-alt.png",
  "/tariff-orange.png",
];

const tariffBackground = (index: number) => ({
  backgroundImage: `linear-gradient(90deg, rgba(7,24,27,.68), rgba(7,24,27,.10)), linear-gradient(135deg, ${tariffAccentColors[index % tariffAccentColors.length].replace(/\.([0-9]+)\)/, (_, alpha) => "." + Math.min(75, Number(alpha) * 2) + ")")}, rgba(7,24,27,.06) 72%), url(${tariffScenes[index % tariffScenes.length]})`,
  backgroundPosition: "center, center, right center",
  backgroundRepeat: "no-repeat",
  backgroundSize: "100% 100%, 100% 100%, 42% 100%",
});

function DemoCatalog({
  onNewTariff,
  onNewProduct,
}: {
  onNewTariff?: () => void;
  onNewProduct?: () => void;
}) {
  const tariffs = [
    ["VIP-зона · Поминутно", "VIP-зона · 1 мин · v2", "0 ₽", true],
    ["dsfdsfdgd", "Обычный зал · 60 мин · v1", "300 ₽", false],
    ["Гостевой 3 минуты", "VIP-зона · 3 мин · v1", "50 ₽", true],
    ["Ночной", "Обычный зал · 660 мин · v1", "500 ₽", true],
    ["Ночной тест", "Обычный зал · 660 мин · v1", "300 ₽", true],
    ["Обычный зал · Поминутно", "Обычный зал · 1 мин · v2", "0 ₽", true],
    ["Тест", "Обычный зал · 3 мин · v1", "50 ₽", true],
    ["Триплкилл · 3 часа (VIP)", "VIP-зона · 180 мин · v1", "400 ₽", true],
    [
      "Триплкилл · 3 часа (Обычный)",
      "Обычный зал · 180 мин · v1",
      "280 ₽",
      true,
    ],
  ] as const;
  const products = [
    ["Live Snack 1787945715", "Товар", "275 ₽", "1 ₽", "2 шт."],
    ["Smoke juice 192557", "Товар", "25 ₽", "1 ₽", "1 шт."],
    ["Кофе", "Напиток", "100 ₽", "64 ₽", "11 шт."],
    ["Кофе 2 порции", "Напиток", "20 ₽", "0 ₽", "1 шт."],
    ["Кофе 3 порции", "Напиток", "20 ₽", "0 ₽", "5 шт."],
    ["Кофе 4 порции", "Напиток", "20 ₽", "0 ₽", "10 шт."],
  ];
  const summary = [
    ["Активные тарифы", "8", "+1 за месяц", Clock3],
    ["Товары в каталоге", "12", "7 напитков · 5 товаров", PackageOpen],
    ["Категории", "5", "Активных категорий", Layers3],
    ["Правила скидок", "1", "1 активное правило", Percent],
  ] as const;
  return (
    <>
      <div
        className="mb-1 flex min-h-20 flex-wrap items-start justify-between gap-3 overflow-hidden border-b border-primary/15! bg-base-100/25! p-3"
        style={{
          backgroundImage:
            "linear-gradient(90deg, rgba(7,24,27,.72), rgba(7,24,27,.24)), url(/neon-club-room.png)",
          backgroundPosition: "center 42%",
          backgroundSize: "cover",
          backgroundRepeat: "no-repeat",
        }}
      >
        <div className="relative z-10">
          <div>
            <p className="mb-1 text-sm text-primary/80!">Операции · Каталог</p>
            <h1 className="text-3xl font-bold tracking-tight">
              Каталог и тарифы
            </h1>
            <p className="mt-1 text-xs text-base-content/70!">
              Каталог клуба: тарифы, товары, остатки и правила скидок.
            </p>
          </div>
        </div>
        <div className="relative z-10 flex flex-wrap gap-2">
          <button className="btn btn-outline btn-sm">
            <Settings size={15} /> Категории
          </button>
          <button className="btn btn-outline btn-sm" onClick={onNewProduct}>
            <Plus size={15} /> Товар
          </button>
          <button className="btn btn-primary btn-sm" onClick={onNewTariff}>
            <Plus size={15} /> Тариф
          </button>
        </div>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {summary.map(([label, value, note, Icon]) => (
          <div
            className="card relative flex-row! min-h-16 items-center gap-2 overflow-hidden border border-primary/25! bg-base-100/85! p-1.5 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md"
            key={label}
          >
            <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Icon size={20} />
            </span>
            <div className="min-w-0 grow">
              <span className="block truncate text-xs leading-tight text-base-content/65!">
                {label}
              </span>
              <strong className="block text-xl font-bold">{value}</strong>
              <small className="block truncate text-[11px] leading-tight text-base-content/55!">
                {note}
              </small>
            </div>
            <Icon size={36} className="shrink-0 text-primary/20" />
          </div>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary/20! bg-base-100/55! p-1 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
        <div className="join">
          <button className="btn btn-primary btn-sm join-item">
            Все позиции
          </button>
          <button className="btn btn-ghost btn-sm join-item">Тарифы</button>
          <button className="btn btn-ghost btn-sm join-item">Товары</button>
        </div>
        <select className="select select-sm ml-auto">
          <option>Все категории</option>
          <option>Напитки</option>
          <option>Товары</option>
        </select>
        <div className="hidden items-center gap-2 px-2 text-xs text-base-content/55! xl:flex">
          <span>Каталог</span>
          <ChevronRight size={13} />
          <strong className="text-base-content/80!">Все позиции</strong>
        </div>
        <label className="flex items-center gap-2 px-2 text-xs text-base-content/65!">
          <input className="toggle toggle-sm toggle-primary" type="checkbox" />{" "}
          Показать архивные
        </label>
      </div>
      <section className="card mb-3 gap-2 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <Clock3 size={17} />
            </span>
            <div>
              <h2 className="font-semibold">Тарифы времени</h2>
              <p className="text-xs text-base-content/60!">
                Активные и архивные тарифы клуба.
              </p>
            </div>
          </div>
          <button className="btn btn-outline btn-sm" onClick={onNewTariff}>
            <Plus size={14} /> Новый тариф
          </button>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
          {tariffs.map(([name, details, price, active], index) => (
            <article
              className="relative min-h-[5.25rem] overflow-hidden rounded-xl border border-primary/25 bg-base-200/80 p-3 leading-tight shadow-[0_10px_26px_rgba(0,0,0,.18)]"
              style={tariffBackground(index)}
              key={name}
            >
              <div className="relative z-10 flex items-center justify-between gap-2">
                <span className="flex items-center gap-1 text-[11px] text-primary">
                  <Clock3 size={12} /> Тариф
                </span>
                <span
                  className={`badge badge-soft badge-xs ${active ? "badge-success" : "badge-neutral"}`}
                >
                  {active ? "Активен" : "Черновик"}
                </span>
              </div>
              <h3 className="relative z-10 mt-1 truncate text-sm font-semibold">
                {name}
              </h3>
              <p className="relative z-10 text-[11px] text-base-content/65!">
                {details}
              </p>
              <div className="relative z-10 mt-1 flex items-end justify-between">
                <strong className="text-base">{price}</strong>
                <button className="btn btn-ghost btn-xs h-5 min-h-5 px-1 text-[10px] text-primary!">
                  {active ? "Архивировать →" : "Опубликовать →"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <PackageOpen size={17} />
            </span>
            <div>
              <h2 className="font-semibold">Товары и напитки</h2>
              <p className="text-xs text-base-content/60!">
                Тип, цена продажи, закупочная цена и текущий остаток.
              </p>
            </div>
          </div>
          <button className="btn btn-outline btn-sm" onClick={onNewProduct}>
            <Plus size={14} /> Добавить товар
          </button>
        </div>
        <div className="overflow-x-auto rounded-lg border border-primary/15! bg-base-200/35 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <div className="grid min-w-[820px] grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-2 border-b border-primary/15! bg-base-200/80 px-3 py-1 text-xs text-base-content/60!">
            <span>Позиция</span>
            <span>Тип</span>
            <span>Продажа</span>
            <span>Закупка</span>
            <span>Остаток</span>
            <span>Действия</span>
          </div>
          {products.map(([name, category, price, cost, stock]) => (
            <div
              className="grid min-w-[820px] grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] items-center gap-2 border-t border-primary/10! px-3 py-2 text-sm"
              key={name}
            >
              <div className="flex items-center gap-2">
                <span className="grid size-6 place-items-center rounded-lg bg-primary/10 text-primary">
                  <ShoppingCart size={13} />
                </span>
                <strong>{name}</strong>
              </div>
              <span>{category}</span>
              <strong>{price}</strong>
              <span>{cost}</span>
              <span className="text-primary">{stock}</span>
              <div className="flex items-center gap-1">
                <button className="btn btn-outline btn-xs">Продать</button>
                <button
                  className="btn btn-ghost btn-square btn-xs text-base-content/70!"
                  aria-label={`Изменить ${name}`}
                >
                  <Edit3 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-warning/12 text-warning">
              <Percent size={17} />
            </span>
            <div>
              <h2 className="font-semibold">Скидки клиентов</h2>
              <p className="text-xs text-base-content/60!">
                Правила скидок применяются при продаже времени.
              </p>
            </div>
          </div>
          <button className="btn btn-outline btn-sm">
            <Plus size={14} /> Новое правило
          </button>
        </div>
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] items-center gap-2 rounded-lg border border-primary/15! bg-base-200/45 px-3 py-1.5 text-xs">
          <strong>админ</strong>
          <span>100%</span>
          <span>Приоритет 0</span>
          <span className="badge badge-success badge-soft badge-sm">
            Активна
          </span>
          <span />
        </div>
      </section>
    </>
  );
}

export function CatalogView({
  api,
  groups,
  tariffs,
  discountRules,
  products,
  categories,
  onRefresh,
  onNewTariff,
  onNewProduct,
  onEditProduct,
  onSellProduct,
  onNewDiscount,
}: {
  api?: GameClubApi;
  groups: BackendWorkstationGroup[];
  tariffs: BackendTariff[];
  discountRules: BackendDiscountRule[];
  products: BackendProduct[];
  categories: BackendProductCategory[];
  onRefresh: () => void;
  onNewTariff?: () => void;
  onNewProduct?: () => void;
  onEditProduct?: (product: BackendProduct) => void;
  onSellProduct?: (product: BackendProduct) => void;
  onNewDiscount?: () => void;
}) {
  const [mode, setMode] = useState<"all" | "tariffs" | "products">("all");
  const [categoryId, setCategoryId] = useState("all");
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [showArchivedTariffs, setShowArchivedTariffs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lifecycleId, setLifecycleId] = useState<string | null>(null);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const groupLabel = (groupId: string | null) =>
    groups.find((group) => group.id === groupId)?.name ??
    (groupId === "vip"
      ? "VIP-зона"
      : groupId === "main"
        ? "Обычный зал"
        : groupId || "Все зоны");
  const categoryName = (id: string) =>
    categories.find((category) => category.id === id)?.name ?? id;
  const visibleProducts =
    categoryId === "all"
      ? products
      : products.filter((product) => product.category === categoryId);
  const visibleTariffs = showArchivedTariffs
    ? tariffs
    : tariffs.filter((tariff) => tariff.lifecycle !== "archived");
  const updateLifecycle = async (tariff: (typeof tariffs)[number]) => {
    if (!api) return;
    setLifecycleId(tariff.id);
    try {
      await (tariff.lifecycle === "draft"
        ? api.publishTariff(tariff.id)
        : api.archiveTariff(tariff.id));
      onRefresh();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось изменить тариф",
      );
    } finally {
      setLifecycleId(null);
    }
  };

  if (!api)
    return (
      <DemoCatalog onNewTariff={onNewTariff} onNewProduct={onNewProduct} />
    );
  return (
    <LiveCatalog
      api={api!}
      tariffs={tariffs}
      discountRules={discountRules}
      products={products}
      categories={categories}
      mode={mode}
      setMode={setMode}
      categoryId={categoryId}
      setCategoryId={setCategoryId}
      showArchivedTariffs={showArchivedTariffs}
      setShowArchivedTariffs={setShowArchivedTariffs}
      visibleTariffs={visibleTariffs}
      visibleProducts={visibleProducts}
      categoryModalOpen={categoryModalOpen}
      setCategoryModalOpen={setCategoryModalOpen}
      error={error}
      lifecycleId={lifecycleId}
      money={money}
      groupLabel={groupLabel}
      categoryName={categoryName}
      updateLifecycle={updateLifecycle}
      onRefresh={onRefresh}
      onNewTariff={onNewTariff}
      onNewProduct={onNewProduct}
      onEditProduct={onEditProduct}
      onSellProduct={onSellProduct}
      onNewDiscount={onNewDiscount}
    />
  );
}

function LiveCatalog({
  api,
  tariffs,
  discountRules,
  products,
  categories,
  mode,
  setMode,
  categoryId,
  setCategoryId,
  showArchivedTariffs,
  setShowArchivedTariffs,
  visibleTariffs,
  visibleProducts,
  categoryModalOpen,
  setCategoryModalOpen,
  error,
  lifecycleId,
  money,
  groupLabel,
  categoryName,
  updateLifecycle,
  onRefresh,
  onNewTariff,
  onNewProduct,
  onEditProduct,
  onSellProduct,
  onNewDiscount,
}: {
  api: GameClubApi;
  tariffs: BackendTariff[];
  discountRules: BackendDiscountRule[];
  products: BackendProduct[];
  categories: BackendProductCategory[];
  mode: "all" | "tariffs" | "products";
  setMode: (value: "all" | "tariffs" | "products") => void;
  categoryId: string;
  setCategoryId: (value: string) => void;
  showArchivedTariffs: boolean;
  setShowArchivedTariffs: (
    value: boolean | ((value: boolean) => boolean),
  ) => void;
  visibleTariffs: BackendTariff[];
  visibleProducts: BackendProduct[];
  categoryModalOpen: boolean;
  setCategoryModalOpen: (value: boolean) => void;
  error: string | null;
  lifecycleId: string | null;
  money: (cents: number) => string;
  groupLabel: (groupId: string | null) => string;
  categoryName: (id: string) => string;
  updateLifecycle: (tariff: BackendTariff) => Promise<void>;
  onRefresh: () => void;
  onNewTariff?: () => void;
  onNewProduct?: () => void;
  onEditProduct?: (product: BackendProduct) => void;
  onSellProduct?: (product: BackendProduct) => void;
  onNewDiscount?: () => void;
}) {
  const summary = [
    [
      "Активные тарифы",
      tariffs.filter((item) => item.lifecycle === "published").length,
      "опубликовано",
      Clock3,
    ],
    ["Товары в каталоге", products.length, "позиций", PackageOpen],
    ["Категории", categories.length, "активных категорий", Layers3],
    ["Правила скидок", discountRules.length, "активных правил", Percent],
  ] as const;
  return (
    <>
      <div className="relative mt-7 mb-4 flex min-h-28 flex-wrap items-start justify-between gap-4 ">
        <div className="relative z-10">
          <div>
            <p className="mb-1 text-sm text-primary/80!">Операции · Каталог</p>
            <h1 className="text-3xl font-bold tracking-tight">
              Каталог и тарифы
            </h1>
            <p className="mt-1 text-sm text-base-content/70!">
              Каталог клуба: тарифы, товары, остатки и правила скидок.
            </p>
          </div>
        </div>
        <div className="heading-actions relative z-10 flex flex-wrap items-center gap-2">
          <button
            className="secondary-button btn btn-outline"
            onClick={() => setCategoryModalOpen(true)}
          >
            <Layers3 size={15} /> Категории
          </button>
          <button
            className="secondary-button btn btn-outline"
            onClick={onNewProduct}
          >
            <Plus size={15} /> Товар
          </button>
          <button
            className="primary-button btn btn-primary"
            onClick={onNewTariff}
          >
            <Plus size={17} /> Тариф
          </button>
        </div>
      </div>
      {error && (
        <div className="alert alert-error mb-3 text-sm" role="alert">
          {error}
        </div>
      )}
      <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {summary.map(([label, value, note, Icon]) => (
          <div
            className="card relative flex-row! min-h-20 items-center gap-2 overflow-hidden border border-primary/25! bg-base-100/85! p-2.5 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md"
            key={label}
          >
            <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <Icon size={22} />
            </span>
            <div className="min-w-0 grow">
              <span className="block truncate text-xs text-base-content/60">
                {label}
              </span>
              <strong className="block text-2xl font-bold text-primary">
                {value}
              </strong>
              <small className="block truncate text-xs text-base-content/55">
                {note}
              </small>
            </div>
            <Icon size={42} className="shrink-0 text-primary/20" />
          </div>
        ))}
      </div>
      <div className="catalog-toolbar mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary/20! bg-base-100/55! p-1.5 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
        <div
          className="compact-tabs join rounded-lg border border-primary/20! bg-base-100/70! p-1"
          role="tablist"
          aria-label="Тип позиции"
        >
          <button
            className={`join-item btn btn-sm ${mode === "all" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70!"}`}
            role="tab"
            aria-selected={mode === "all"}
            onClick={() => setMode("all")}
          >
            Все позиции
          </button>
          <button
            className={`join-item btn btn-sm ${mode === "tariffs" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70!"}`}
            role="tab"
            aria-selected={mode === "tariffs"}
            onClick={() => setMode("tariffs")}
          >
            Тарифы
          </button>
          <button
            className={`join-item btn btn-sm ${mode === "products" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70!"}`}
            role="tab"
            aria-selected={mode === "products"}
            onClick={() => setMode("products")}
          >
            Товары
          </button>
        </div>
        <select
          className="select select-sm"
          aria-label="Фильтр категории товара"
          value={categoryId}
          onChange={(event) => setCategoryId(event.target.value)}
        >
          <option value="all">Все категории</option>
          {categories.map((category) => (
            <option value={category.id} key={category.id}>
              {category.name}
            </option>
          ))}
        </select>
        <span className="flex items-center gap-1 text-xs text-base-content/60">
          Каталог <ChevronRight size={13} />{" "}
          {mode === "all"
            ? "Все позиции"
            : mode === "tariffs"
              ? "Тарифы"
              : "Товары"}
        </span>
        <label className="ml-auto flex items-center gap-2 text-xs text-base-content/65">
          <input
            className="toggle toggle-sm toggle-primary"
            type="checkbox"
            checked={showArchivedTariffs}
            onChange={(event) => setShowArchivedTariffs(event.target.checked)}
          />{" "}
          Показать архивные
        </label>
      </div>
      {mode !== "products" && (
        <section className="card mb-3 gap-2 border border-primary/25! bg-base-100/85! p-3 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Clock3 size={18} className="text-primary" />
                <h2 className="text-lg font-semibold">Тарифы времени</h2>
              </div>
              <p className="text-sm text-base-content/60">
                Активные и архивные тарифы клуба.
              </p>
            </div>
            <button className="btn btn-outline btn-sm" onClick={onNewTariff}>
              <Plus size={14} /> Новый тариф
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
            {visibleTariffs.map((tariff, index) => (
              <article
                className={`card relative min-h-0! gap-0! overflow-hidden border border-primary/25! bg-base-100/80! p-1.5 leading-tight shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_18px_rgba(49,217,120,0.08)] backdrop-blur-md ${tariff.lifecycle === "published" ? "" : "opacity-70"}`}
                style={tariffBackground(index)}
                key={tariff.id}
              >
                <div className="relative z-10 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1 text-[11px] text-primary">
                    <Clock3 size={12} /> Тариф
                  </span>
                  <span
                    className={`badge badge-soft badge-xs ${tariff.lifecycle === "published" ? "badge-success" : "badge-neutral"}`}
                  >
                    {tariff.lifecycle === "published"
                      ? "Активен"
                      : tariff.lifecycle === "draft"
                        ? "Черновик"
                        : "Архив"}
                  </span>
                </div>
                <h3 className="relative z-10 truncate text-xs font-semibold">
                  {tariff.name}
                </h3>
                <p className="relative z-10 text-[11px] text-base-content/65">
                  {groupLabel(tariff.group_id)} · {tariff.duration_minutes} мин
                  · v{tariff.version}
                </p>
                <div className="relative z-10 flex items-end justify-between gap-2">
                  <strong className="text-sm">
                    {money(tariff.price_cents)}
                  </strong>
                  {tariff.lifecycle !== "archived" && (
                    <button
                      className="btn btn-ghost btn-xs h-5 min-h-5 px-1 text-[10px]"
                      disabled={lifecycleId === tariff.id}
                      onClick={() => void updateLifecycle(tariff)}
                    >
                      {tariff.lifecycle === "draft"
                        ? "Опубликовать"
                        : "Архивировать"}{" "}
                      <MoreHorizontal size={12} />
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      {mode !== "tariffs" && (
        <section className="card mb-3 gap-2 border border-primary/25! bg-base-100/85! p-3 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <PackageOpen size={18} className="text-primary" />
                <h2 className="text-lg font-semibold">Товары и напитки</h2>
              </div>
              <p className="text-sm text-base-content/60">
                Тип, цена продажи, закупочная цена и текущий остаток.
              </p>
            </div>
            <button className="btn btn-outline btn-sm" onClick={onNewProduct}>
              <Plus size={14} /> Добавить товар
            </button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-primary/15! bg-base-200/35 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <div className="grid min-w-[720px] grid-cols-[2fr_repeat(4,minmax(90px,1fr))_auto] gap-2 border-b border-primary/15! bg-base-200/80 px-3 py-1.5 text-xs text-base-content/60">
              <span>Позиция</span>
              <span>Тип</span>
              <span>Продажа</span>
              <span>Закупка</span>
              <span>Остаток</span>
              <span>Действия</span>
            </div>
            {visibleProducts.map((product) => (
              <div
                className="grid min-w-[720px] grid-cols-[2fr_repeat(4,minmax(90px,1fr))_auto] items-center gap-2 border-t border-primary/10! px-3 py-1.5 text-sm"
                key={product.id}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <PackageOpen size={14} />
                  </span>
                  <div className="min-w-0">
                    <strong className="block truncate">{product.name}</strong>
                    <small className="block text-xs text-base-content/55">
                      {categoryName(product.category)}
                    </small>
                  </div>
                </div>
                <span className="badge badge-ghost badge-sm">
                  {categories.find(
                    (category) => category.id === product.category,
                  )?.kind === "drink"
                    ? "Напиток"
                    : "Товар"}
                </span>
                <strong>{money(product.price_cents)}</strong>
                <span>{money(product.cost_price_cents)}</span>
                <span
                  className={
                    product.stock_quantity <= 5
                      ? "text-warning"
                      : "text-primary"
                  }
                >
                  {product.stock_quantity} шт.
                </span>
                <div className="flex items-center gap-1">
                  <button
                    className="btn btn-outline btn-xs"
                    aria-label={`Продать товар ${product.name}`}
                    onClick={() => onSellProduct?.(product)}
                    disabled={
                      !onSellProduct ||
                      !product.active ||
                      product.stock_quantity < 1
                    }
                  >
                    <ShoppingCart size={13} /> Продать
                  </button>
                  <button
                    className="btn btn-ghost btn-circle btn-xs"
                    aria-label={`Редактировать товар ${product.name}`}
                    onClick={() => onEditProduct?.(product)}
                  >
                    <Edit3 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="card gap-3 border border-primary/25! bg-base-100/85! p-4 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Percent size={18} className="text-warning" />
              <h2 className="text-lg font-semibold">Скидки клиентов</h2>
            </div>
            <p className="text-sm text-base-content/60">
              Правила скидок применяются при продаже времени.
            </p>
          </div>
          <button className="btn btn-outline btn-sm" onClick={onNewDiscount}>
            <Plus size={14} /> Новое правило
          </button>
        </div>
        {discountRules.length ? (
          <div className="overflow-x-auto rounded-lg border border-primary/15! bg-base-200/35 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <div className="grid min-w-[560px] grid-cols-[2fr_1fr_1fr_1fr_auto] gap-3 border-b border-primary/15! bg-base-200/80 px-3 py-2 text-xs text-base-content/60">
              <span>Название</span>
              <span>Размер скидки</span>
              <span>Приоритет</span>
              <span>Статус</span>
              <span />
            </div>
            {discountRules.map((rule) => (
              <div
                className="grid min-w-[560px] grid-cols-[2fr_1fr_1fr_1fr_auto] items-center gap-3 border-t border-primary/10! px-3 py-2.5 text-sm"
                key={rule.id}
              >
                <strong>{rule.category}</strong>
                <span>{(rule.percent_bps / 100).toLocaleString("ru-RU")}%</span>
                <span>{rule.priority}</span>
                <span className="badge badge-success badge-soft badge-sm">
                  {rule.active ? "Активна" : "Отключена"}
                </span>
                <span />
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-4 text-sm text-base-content/60">
            Правил скидок пока нет.
          </div>
        )}
      </section>
      {categoryModalOpen && (
        <div
          className="modal-backdrop fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
          role="presentation"
          onClick={() => setCategoryModalOpen(false)}
        >
          <div
            className="modal-card max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-primary/30! bg-base-100/95! p-5 text-base-content! shadow-[0_0_32px_rgba(49,217,120,0.12),0_25px_80px_rgba(0,0,0,0.42)] backdrop-blur-xl"
            role="dialog"
            aria-modal="true"
            aria-label="Категории товаров и напитков"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <p className="mb-1 text-sm text-base-content/65!">Каталог</p>
                <h2>Категории</h2>
              </div>
              <button
                className="btn btn-ghost btn-circle btn-sm"
                aria-label="Закрыть категории"
                onClick={() => setCategoryModalOpen(false)}
              >
                <X size={18} />
              </button>
            </div>
            <ProductCategoryManager
              api={api}
              categories={categories}
              onCategoriesChange={onRefresh}
            />
          </div>
        </div>
      )}
    </>
  );
}

export function ProductCategoryManager({
  api,
  categories,
  onCategoriesChange,
}: {
  api: GameClubApi;
  categories: BackendProductCategory[];
  onCategoriesChange: () => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BackendProductCategory["kind"]>("product");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingKind, setEditingKind] =
    useState<BackendProductCategory["kind"]>("product");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const create = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Укажите название категории");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createProductCategory({ name: name.trim(), kind });
      onCategoriesChange();
      setName("");
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось создать категорию",
      );
    } finally {
      setSaving(false);
    }
  };

  const save = async (category: BackendProductCategory) => {
    if (!editingName.trim()) {
      setError("Название категории не может быть пустым");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateProductCategory(category.id, {
        name: editingName.trim(),
        kind: editingKind,
      });
      onCategoriesChange();
      setEditingId(null);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось изменить категорию",
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = async (category: BackendProductCategory) => {
    if (
      !window.confirm(
        `Удалить категорию «${category.name}»? Товары не удаляются.`,
      )
    )
      return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteProductCategory(category.id);
      onCategoriesChange();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось удалить категорию",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card category-manager gap-3 border border-primary/25! bg-base-100/90! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.1)] backdrop-blur-md">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3>Категории товаров и напитков</h3>
          <p>Создавайте, переименовывайте и удаляйте группы каталога.</p>
        </div>
        <span className="badge badge-success badge-soft badge-sm">
          {categories.length}
        </span>
      </div>
      <form
        className="category-create-form flex flex-wrap items-center gap-2"
        onSubmit={(event) => void create(event)}
      >
        <input
          className="input input-sm"
          aria-label="Название новой категории"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Например, Напитки"
        />
        <select
          className="select select-sm"
          aria-label="Тип новой категории"
          value={kind}
          onChange={(event) =>
            setKind(event.target.value as BackendProductCategory["kind"])
          }
        >
          <option value="product">Товары</option>
          <option value="drink">Напитки</option>
        </select>
        <button className="secondary-button btn btn-outline" disabled={saving}>
          <Plus size={15} /> Добавить
        </button>
      </form>
      {error && (
        <div
          className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {error}
        </div>
      )}
      {categories.map((category) =>
        editingId === category.id ? (
          <div
            className="category-row flex flex-wrap items-center gap-2 border-t border-primary/15! py-3"
            key={category.id}
          >
            <input
              className="input input-sm"
              aria-label="Название категории"
              value={editingName}
              onChange={(event) => setEditingName(event.target.value)}
            />
            <select
              className="select select-sm"
              aria-label="Тип категории"
              value={editingKind}
              onChange={(event) =>
                setEditingKind(
                  event.target.value as BackendProductCategory["kind"],
                )
              }
            >
              <option value="product">Товары</option>
              <option value="drink">Напитки</option>
            </select>
            <button
              className="text-button btn btn-ghost btn-sm"
              disabled={saving}
              onClick={() => void save(category)}
            >
              Сохранить
            </button>
            <button
              className="icon-button btn btn-ghost btn-circle btn-sm"
              aria-label="Отменить редактирование"
              onClick={() => setEditingId(null)}
            >
              <X size={15} />
            </button>
          </div>
        ) : (
          <div
            className="category-row flex flex-wrap items-center gap-2 border-t border-primary/15! py-3"
            key={category.id}
          >
            <div>
              <strong>{category.name}</strong>
              <span>
                {category.kind === "drink" ? "Напитки" : "Товары"} ·{" "}
                {category.id}
              </span>
            </div>
            <button
              className="text-button btn btn-ghost btn-sm"
              onClick={() => {
                setEditingId(category.id);
                setEditingName(category.name);
                setEditingKind(category.kind);
              }}
            >
              Изменить
            </button>
            <button
              className="text-button danger-text btn btn-error btn-outline"
              disabled={saving}
              onClick={() => void remove(category)}
            >
              Удалить
            </button>
          </div>
        ),
      )}
      {!categories.length && (
        <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
          Категорий пока нет — создайте первую выше.
        </div>
      )}
    </div>
  );
}

export function TariffPanel({
  api,
  groups,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  groups: BackendWorkstationGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState("main");
  const [duration, setDuration] = useState("60");
  const [price, setPrice] = useState("300");
  const [timeRestricted, setTimeRestricted] = useState(false);
  const [saleFrom, setSaleFrom] = useState("22:00");
  const [saleTo, setSaleTo] = useState("06:00");
  const [usageFrom, setUsageFrom] = useState("22:00");
  const [usageTo, setUsageTo] = useState("06:00");
  const [timezone, setTimezone] = useState("Europe/Moscow");
  const [audience, setAudience] =
    useState<NonNullable<BackendTariff["audience"]>>("all");
  const [validFrom, setValidFrom] = useState(() => {
    const date = new Date();
    date.setSeconds(0, 0);
    return localDateTimeValue(date);
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const durationMinutes = Number(duration);
    const priceRubles = Number(price);
    if (
      !name.trim() ||
      !Number.isInteger(durationMinutes) ||
      durationMinutes <= 0 ||
      !Number.isFinite(priceRubles) ||
      priceRubles < 0
    ) {
      setError("Заполните название, длительность и корректную цену");
      return;
    }
    const parsedDate = new Date(validFrom);
    if (Number.isNaN(parsedDate.getTime())) {
      setError("Укажите дату начала действия тарифа");
      return;
    }
    const toMinute = (value: string) => {
      const [hours, minutes] = value.split(":").map(Number);
      return Number.isInteger(hours) && Number.isInteger(minutes)
        ? hours * 60 + minutes
        : null;
    };
    const saleStart = toMinute(saleFrom);
    const saleEnd = toMinute(saleTo);
    const usageStart = toMinute(usageFrom);
    const usageEnd = toMinute(usageTo);
    if (
      timeRestricted &&
      (saleStart === null ||
        saleEnd === null ||
        usageStart === null ||
        usageEnd === null ||
        saleStart === saleEnd ||
        usageStart === usageEnd ||
        !timezone.trim())
    ) {
      setError(
        "Для временного тарифа укажите два непустых окна и часовой пояс",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createTariff({
        name: name.trim(),
        group_id: groupId || null,
        duration_minutes: durationMinutes,
        price_cents: Math.round(priceRubles * 100),
        billing_mode: "block",
        valid_from: parsedDate.toISOString(),
        lifecycle: "draft",
        time_restricted: timeRestricted,
        sale_window_start_minute: timeRestricted
          ? (saleStart ?? undefined)
          : undefined,
        sale_window_end_minute: timeRestricted
          ? (saleEnd ?? undefined)
          : undefined,
        usage_window_start_minute: timeRestricted
          ? (usageStart ?? undefined)
          : undefined,
        usage_window_end_minute: timeRestricted
          ? (usageEnd ?? undefined)
          : undefined,
        window_timezone: timeRestricted ? timezone.trim() : undefined,
        audience,
      });
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось создать тариф",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const tariffGroups = groups.length
    ? groups
    : [
        { id: "main", name: "Обычный зал" },
        { id: "vip", name: "VIP-зона" },
      ];
  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <div className="panel-header flex items-start justify-between gap-3 border-b border-primary/15! pb-4">
        <div>
          <p>Настройки клуба</p>
          <h2>Новый пакет времени</h2>
        </div>
        <button
          className="icon-button btn btn-ghost btn-circle btn-sm"
          aria-label="Закрыть панель"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Название
          <input
            className="input input-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Пакет 1 час"
            autoFocus
          />
        </label>
        <label>
          Зона
          <select
            className="select select-sm"
            value={groupId}
            onChange={(event) => setGroupId(event.target.value)}
          >
            {tariffGroups.map((group) => (
              <option value={group.id} key={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-grid-two grid grid-cols-1 gap-3 md:grid-cols-2">
          <label>
            Длительность, минут
            <input
              className="input input-sm"
              type="number"
              min="1"
              step="1"
              value={duration}
              onChange={(event) => setDuration(event.target.value)}
            />
          </label>
          <label>
            Цена пакета, ₽
            <input
              className="input input-sm"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
            />
          </label>
        </div>
        <label>
          Для кого доступен тариф
          <select
            className="select select-sm"
            value={audience}
            onChange={(event) =>
              setAudience(
                event.target.value as NonNullable<BackendTariff["audience"]>,
              )
            }
          >
            <option value="all">Гости и зарегистрированные</option>
            <option value="guest">Только гости</option>
            <option value="registered">Только зарегистрированные</option>
          </select>
        </label>
        <label>
          Начало действия
          <DateTimePicker
            value={validFrom}
            onChange={setValidFrom}
            mode="datetime"
            label="Начало действия тарифа"
          />
        </label>
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input
            className="toggle toggle-primary toggle-sm"
            type="checkbox"
            checked={timeRestricted}
            onChange={(event) => setTimeRestricted(event.target.checked)}
          />{" "}
          Ограничить тариф ежедневными окнами
        </label>
        {timeRestricted && (
          <>
            <div className="form-grid-two grid grid-cols-1 gap-3 md:grid-cols-2">
              <label>
                Показывать и продавать с
                <input
                  className="input input-sm"
                  type="time"
                  value={saleFrom}
                  onChange={(event) => setSaleFrom(event.target.value)}
                />
              </label>
              <label>
                до
                <input
                  className="input input-sm"
                  type="time"
                  value={saleTo}
                  onChange={(event) => setSaleTo(event.target.value)}
                />
              </label>
            </div>
            <div className="form-grid-two grid grid-cols-1 gap-3 md:grid-cols-2">
              <label>
                Расходовать время с
                <input
                  className="input input-sm"
                  type="time"
                  value={usageFrom}
                  onChange={(event) => setUsageFrom(event.target.value)}
                />
              </label>
              <label>
                до
                <input
                  className="input input-sm"
                  type="time"
                  value={usageTo}
                  onChange={(event) => setUsageTo(event.target.value)}
                />
              </label>
            </div>
            <label>
              Часовой пояс
              <input
                className="input input-sm"
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                placeholder="Europe/Moscow"
              />
            </label>
            <p className="mt-1 text-sm text-base-content/65!">
              Окна повторяются каждый день, включая переход через полночь.
            </p>
          </>
        )}
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
          {submitting ? "Сохраняем..." : "Создать тариф"}
        </button>
        <p className="mt-1 text-sm text-base-content/65!">
          Поминутная ставка и бесплатные минуты настраиваются в карточке зоны.
        </p>
      </form>
    </div>
  );
}

export function ProductPanel({
  api,
  product,
  categories,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  product?: BackendProduct;
  categories: BackendProductCategory[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState(product?.category ?? "");
  const [price, setPrice] = useState(
    product ? String(product.price_cents / 100) : "0",
  );
  const [costPrice, setCostPrice] = useState(
    product ? String(product.cost_price_cents / 100) : "0",
  );
  const [stock, setStock] = useState(
    product ? String(product.stock_quantity) : "0",
  );
  const [active, setActive] = useState(product?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setCategory((current) => current || categories[0]?.id || "");
  }, [categories]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const priceRubles = Number(price.replace(",", "."));
    const costRubles = Number(costPrice.replace(",", "."));
    const stockQuantity = Number(stock);
    if (
      !name.trim() ||
      !category.trim() ||
      !Number.isFinite(priceRubles) ||
      priceRubles < 0 ||
      !Number.isFinite(costRubles) ||
      costRubles < 0 ||
      !Number.isInteger(stockQuantity) ||
      stockQuantity < 0
    ) {
      setError("Заполните позицию, категорию, цены и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        name: name.trim(),
        category: category.trim(),
        price_cents: Math.round(priceRubles * 100),
        cost_price_cents: Math.round(costRubles * 100),
        stock_quantity: stockQuantity,
        active,
      };
      if (product) await api.updateProduct(product.id, payload);
      else await api.createProduct(payload);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить товар",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!product || !window.confirm(`Удалить товар «${product.name}»?`)) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.deleteProduct(product.id);
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось удалить товар",
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title={product ? "Редактирование товара" : "Новый товар"}
        subtitle="Каталог · позиция"
        onClose={onClose}
      />
      <form
        className="flex flex-col gap-3 text-sm"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          Название
          <input
            className="input input-sm ml-2"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Кофе"
            autoFocus
          />
        </label>
        <label>
          Категория
          <select
            className="select select-sm ml-2"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            disabled={!categories.length}
          >
            <option value="">
              {categories.length
                ? "Выберите категорию"
                : "Сначала создайте категорию"}
            </option>
            {categories.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name} · {item.kind === "drink" ? "напитки" : "товары"}
              </option>
            ))}
          </select>
        </label>
        <div className="form-grid-two grid grid-cols-1 gap-3 md:grid-cols-2">
          <label>
            Цена продажи, ₽
            <input
              className="input input-sm"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
            />
          </label>
          <label>
            Закупочная цена, ₽
            <input
              className="input input-sm"
              type="number"
              min="0"
              step="0.01"
              value={costPrice}
              onChange={(event) => setCostPrice(event.target.value)}
            />
          </label>
        </div>
        <div className="form-grid-two grid grid-cols-1 gap-3 md:grid-cols-2">
          <label>
            Остаток, шт.
            <input
              className="input input-sm"
              type="number"
              min="0"
              step="1"
              value={stock}
              onChange={(event) => setStock(event.target.value)}
            />
          </label>
          <div className="col-span-2">
            <label className="flex cursor-pointer justify-center items-center gap-3 text-sm">
              <input
                className="toggle toggle-primary toggle-sm flex-ro"
                type="checkbox"
                checked={active}
                onChange={(event) => setActive(event.target.checked)}
              />{" "}
              <span className="whitespace-nowrap">Позиция активна</span>
            </label>
          </div>
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
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting || !categories.length}
        >
          {submitting
            ? "Сохраняем..."
            : product
              ? "Сохранить изменения"
              : "Создать товар"}
        </button>
      </form>
      {product && (
        <button
          className="danger-button btn btn-error btn-outline btn-block product-delete-button"
          onClick={() => void remove()}
          disabled={submitting}
        >
          Удалить товар <ChevronRight size={15} />
        </button>
      )}
    </div>
  );
}

export function DiscountPanel({
  api,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [category, setCategory] = useState("");
  const [percent, setPercent] = useState("0");
  const [priority, setPriority] = useState("0");
  const [validFrom, setValidFrom] = useState(() => {
    const date = new Date();
    date.setSeconds(0, 0);
    return localDateTimeValue(date);
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const percentValue = Number(percent);
    const priorityValue = Number(priority);
    const parsedDate = new Date(validFrom);
    if (
      !category.trim() ||
      !Number.isFinite(percentValue) ||
      percentValue < 0 ||
      percentValue > 100 ||
      !Number.isInteger(priorityValue) ||
      priorityValue < 0 ||
      Number.isNaN(parsedDate.getTime())
    ) {
      setError("Заполните категорию, процент от 0 до 100 и приоритет");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createDiscountRule({
        category: category.trim(),
        percent_bps: Math.round(percentValue * 100),
        priority: priorityValue,
        valid_from: parsedDate.toISOString(),
      });
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось создать правило скидки",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <div className="panel-header flex items-start justify-between gap-3 border-b border-primary/15! pb-4">
        <div>
          <p>Каталог</p>
          <h2>Новая скидка</h2>
        </div>
        <button
          className="icon-button btn btn-ghost btn-circle btn-sm"
          aria-label="Закрыть панель"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Категория клиента
          <input
            className="input input-sm"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="student"
            autoFocus
          />
        </label>
        <label>
          Скидка, %
          <input
            className="input input-sm"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={percent}
            onChange={(event) => setPercent(event.target.value)}
          />
        </label>
        <label>
          Приоритет
          <input
            className="input input-sm"
            type="number"
            min="0"
            step="1"
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
          />
        </label>
        <label>
          Начало действия
          <DateTimePicker
            value={validFrom}
            onChange={setValidFrom}
            mode="datetime"
            label="Начало действия правила"
          />
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
          disabled={submitting}
        >
          {submitting ? "Сохраняем..." : "Создать правило"}
        </button>
        <p className="mt-1 text-sm text-base-content/65!">
          При продаже будет использована самая приоритетная подходящая скидка.
        </p>
      </form>
    </div>
  );
}
