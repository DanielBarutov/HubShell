import { useEffect, useState } from "react";
import { ChevronRight, Clock3, Edit3, Plus, ShoppingCart, Settings, X } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendProduct, BackendProductCategory, BackendWorkstationGroup } from "../../api";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { localDateTimeValue } from "../../shared/formatters";

export function CatalogView({ api, groups, refreshKey, onNewTariff, onNewProduct, onEditProduct, onSellProduct, onNewDiscount }: { api?: GameClubApi; groups: BackendWorkstationGroup[]; refreshKey: number; onNewTariff?: () => void; onNewProduct?: () => void; onEditProduct?: (product: BackendProduct) => void; onSellProduct?: (product: BackendProduct) => void; onNewDiscount?: () => void }) {
  const [tariffs, setTariffs] = useState<Awaited<ReturnType<GameClubApi["listTariffs"]>>>([]);
  const [discountRules, setDiscountRules] = useState<Awaited<ReturnType<GameClubApi["listDiscountRules"]>>>([]);
  const [products, setProducts] = useState<BackendProduct[]>([]);
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [mode, setMode] = useState<"all" | "tariffs" | "products">("all");
  const [categoryId, setCategoryId] = useState("all");
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [showArchivedTariffs, setShowArchivedTariffs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lifecycleId, setLifecycleId] = useState<string | null>(null);

  useEffect(() => {
    if (!api) return undefined;
    let active = true;
    void Promise.all([api.listTariffs(), api.listDiscountRules(), api.listProducts(), api.listProductCategories()]).then(([tariffItems, ruleItems, productItems, categoryItems]) => {
      if (active) {
        setTariffs(tariffItems.filter((item) => item.billing_mode === "block"));
        setDiscountRules(ruleItems);
        setProducts(productItems);
        setCategories(categoryItems);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить каталог");
    });
    return () => { active = false; };
  }, [api, refreshKey]);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const groupLabel = (groupId: string | null) => groups.find((group) => group.id === groupId)?.name ?? (groupId === "vip" ? "VIP-зона" : groupId === "main" ? "Обычный зал" : groupId || "Все зоны");
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? id;
  const visibleProducts = categoryId === "all" ? products : products.filter((product) => product.category === categoryId);
  const visibleTariffs = showArchivedTariffs ? tariffs : tariffs.filter((tariff) => tariff.lifecycle !== "archived");
  const updateLifecycle = async (tariff: (typeof tariffs)[number]) => {
    if (!api) return;
    setLifecycleId(tariff.id);
    try {
      const updated = tariff.lifecycle === "draft" ? await api.publishTariff(tariff.id) : await api.archiveTariff(tariff.id);
      setTariffs((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить тариф");
    } finally {
      setLifecycleId(null);
    }
  };

  if (!api) return <div className="catalog-empty-state"><p className="eyebrow">Настройки клуба</p><h1>Каталог</h1><p className="subheading">Live-режим подключает тарифы, товары, категории и складские остатки.</p></div>;
  return <><div className="page-heading"><div><p className="eyebrow">Операции · Каталог</p><h1>Каталог клуба</h1><p className="subheading">Тарифы времени, товары и остатки — в одном рабочем списке.</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => setCategoryModalOpen(true)}><Settings size={15} /> Категории</button><button className="secondary-button" onClick={onNewProduct}><Plus size={15} /> Товар</button><button className="primary-button" onClick={onNewTariff}><Plus size={17} /> Тариф</button></div></div>{error && <div className="search-hint error" role="alert">{error}</div>}<div className="catalog-summary"><div><span>Тарифы</span><strong>{tariffs.filter((item) => item.lifecycle === "published").length}</strong><small>опубликовано</small></div><div><span>Товары</span><strong>{products.length}</strong><small>позиций</small></div><div><span>Категории</span><strong>{categories.length}</strong><small>групп каталога</small></div><div><span>Скидки</span><strong>{discountRules.length}</strong><small>активных правил</small></div></div><div className="catalog-toolbar"><div className="compact-tabs" role="tablist" aria-label="Тип позиции"><button className={mode === "all" ? "selected" : ""} role="tab" aria-selected={mode === "all"} onClick={() => setMode("all")}>Все позиции</button><button className={mode === "tariffs" ? "selected" : ""} role="tab" aria-selected={mode === "tariffs"} onClick={() => setMode("tariffs")}>Тарифы</button><button className={mode === "products" ? "selected" : ""} role="tab" aria-selected={mode === "products"} onClick={() => setMode("products")}>Товары</button></div><select className="catalog-category-filter" aria-label="Фильтр категории товара" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="all">Все категории</option>{categories.map((category) => <option value={category.id} key={category.id}>{category.name}</option>)}</select><span className="catalog-breadcrumb">Каталог <ChevronRight size={13} /> {mode === "all" ? "Все позиции" : mode === "tariffs" ? "Тарифы времени" : "Товары и напитки"}</span><button className={`archive-toggle ${showArchivedTariffs ? "active" : ""}`} type="button" aria-pressed={showArchivedTariffs} onClick={() => setShowArchivedTariffs((value) => !value)}>{showArchivedTariffs ? "Скрыть архивные" : "Показать архивные"}</button></div>{mode !== "products" && <section className="catalog-section"><div className="section-row"><div><h2>Тарифы времени</h2><p className="section-caption">{showArchivedTariffs ? "Активные, черновики и архивные версии." : "Активные и черновики · архивные скрыты."}</p></div><button className="text-button" onClick={onNewTariff}><Plus size={14} /> Новый тариф</button></div><div className="tariff-mini-grid">{visibleTariffs.map((tariff) => <article className={`tariff-mini-card ${tariff.lifecycle === "published" ? "" : "muted"}`} key={tariff.id}><div className="tariff-mini-top"><span className="tariff-type"><Clock3 size={13} /> Тариф</span><span className={`active-chip ${tariff.lifecycle === "published" ? "" : "inactive"}`}>{tariff.lifecycle === "published" ? "Активен" : tariff.lifecycle === "draft" ? "Черновик" : "Архив"}</span></div><h3>{tariff.name}</h3><p>{groupLabel(tariff.group_id)} · {tariff.duration_minutes} мин · v{tariff.version}</p><strong>{money(tariff.price_cents)}</strong><div className="tariff-mini-actions">{tariff.lifecycle !== "archived" && <button className="text-button" disabled={lifecycleId === tariff.id} onClick={() => void updateLifecycle(tariff)}>{tariff.lifecycle === "draft" ? "Опубликовать" : "Архивировать"}</button>}</div></article>)}{!visibleTariffs.length && <div className="empty-state-card">{tariffs.length ? "Архивные тарифы скрыты. Нажмите «Показать архивные», чтобы просмотреть историю." : "Тарифов пока нет. Создайте первое правило времени."}</div>}</div></section>}{mode !== "tariffs" && <section className="catalog-section"><div className="section-row"><div><h2>Товары и напитки</h2><p className="section-caption">Тип, цена продажи, закупочная цена и текущий остаток.</p></div><button className="text-button" onClick={onNewProduct}><Plus size={14} /> Добавить товар</button></div><div className="product-table"><div className="product-table-head"><span>Позиция</span><span>Тип</span><span>Продажа</span><span>Закупка</span><span>Остаток</span><span>Действия</span></div>{visibleProducts.map((product) => <div className="product-table-row" key={product.id}><div><strong>{product.name}</strong><small>{categoryName(product.category)}</small></div><span className="product-kind-chip">{categories.find((category) => category.id === product.category)?.kind === "drink" ? "Напиток" : "Товар"}</span><strong>{money(product.price_cents)}</strong><span>{money(product.cost_price_cents)}</span><span className={product.stock_quantity <= 5 ? "stock-low" : "stock-ok"}>{product.stock_quantity} шт.</span><div className="product-row-actions"><button className="secondary-button compact-action" aria-label={`Продать товар ${product.name}`} onClick={() => onSellProduct?.(product)} disabled={!onSellProduct || !product.active || product.stock_quantity < 1}><ShoppingCart size={13} /> Продать</button><button className="icon-button small" aria-label={`Редактировать товар ${product.name}`} onClick={() => onEditProduct?.(product)}><Edit3 size={14} /></button></div></div>)}{!visibleProducts.length && <div className="empty-state-card">По выбранной категории товаров нет.</div>}</div></section>}<section className="catalog-section discount-section"><div className="section-row"><div><h2>Скидки клиентов</h2><p className="section-caption">Категория клиента применяется backend-расчётом при продаже времени.</p></div><button className="text-button" onClick={onNewDiscount}><Plus size={14} /> Новое правило</button></div>{discountRules.length ? <div className="discount-compact-list">{discountRules.map((rule) => <div className="discount-compact-row" key={rule.id}><span className="product-kind-chip">{rule.category}</span><strong>{(rule.percent_bps / 100).toLocaleString("ru-RU")}%</strong><span>Приоритет {rule.priority}</span><span className="active-chip">{rule.active ? "Активна" : "Отключена"}</span></div>)}</div> : <div className="empty-state-card">Правил скидок пока нет.</div>}</section>{categoryModalOpen && <div className="modal-backdrop" role="presentation" onClick={() => setCategoryModalOpen(false)}><div className="modal-card" role="dialog" aria-modal="true" aria-label="Категории товаров и напитков" onClick={(event) => event.stopPropagation()}><div className="modal-card-head"><div><p className="eyebrow">Каталог</p><h2>Категории</h2></div><button className="icon-button" aria-label="Закрыть категории" onClick={() => setCategoryModalOpen(false)}><X size={18} /></button></div><ProductCategoryManager api={api} categories={categories} onCategoriesChange={setCategories} /></div></div>}</>;
}

export function ProductCategoryManager({ api, categories, onCategoriesChange }: { api: GameClubApi; categories: BackendProductCategory[]; onCategoriesChange: (categories: BackendProductCategory[]) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BackendProductCategory["kind"]>("product");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingKind, setEditingKind] = useState<BackendProductCategory["kind"]>("product");
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
      const created = await api.createProductCategory({ name: name.trim(), kind });
      onCategoriesChange([...categories, created]);
      setName("");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать категорию");
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
      const updated = await api.updateProductCategory(category.id, { name: editingName.trim(), kind: editingKind });
      onCategoriesChange(categories.map((item) => item.id === updated.id ? updated : item));
      setEditingId(null);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить категорию");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (category: BackendProductCategory) => {
    if (!window.confirm(`Удалить категорию «${category.name}»? Товары не удаляются.`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteProductCategory(category.id);
      onCategoriesChange(categories.filter((item) => item.id !== category.id));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить категорию");
    } finally {
      setSaving(false);
    }
  };

  return <div className="white-card product-list-card category-manager"><div className="card-heading"><div><h3>Категории товаров и напитков</h3><p>Создавайте, переименовывайте и удаляйте группы каталога.</p></div><span className="active-chip">{categories.length}</span></div><form className="category-create-form" onSubmit={(event) => void create(event)}><input aria-label="Название новой категории" value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Напитки" /><select aria-label="Тип новой категории" value={kind} onChange={(event) => setKind(event.target.value as BackendProductCategory["kind"])}><option value="product">Товары</option><option value="drink">Напитки</option></select><button className="secondary-button" disabled={saving}><Plus size={15} /> Добавить</button></form>{error && <div className="form-error" role="alert">{error}</div>}{categories.map((category) => editingId === category.id ? <div className="category-row" key={category.id}><input aria-label="Название категории" value={editingName} onChange={(event) => setEditingName(event.target.value)} /><select aria-label="Тип категории" value={editingKind} onChange={(event) => setEditingKind(event.target.value as BackendProductCategory["kind"])}><option value="product">Товары</option><option value="drink">Напитки</option></select><button className="text-button" disabled={saving} onClick={() => void save(category)}>Сохранить</button><button className="icon-button" aria-label="Отменить редактирование" onClick={() => setEditingId(null)}><X size={15} /></button></div> : <div className="category-row" key={category.id}><div><strong>{category.name}</strong><span>{category.kind === "drink" ? "Напитки" : "Товары"} · {category.id}</span></div><button className="text-button" onClick={() => { setEditingId(category.id); setEditingName(category.name); setEditingKind(category.kind); }}>Изменить</button><button className="text-button danger-text" disabled={saving} onClick={() => void remove(category)}>Удалить</button></div>)}{!categories.length && <div className="timeline-empty">Категорий пока нет — создайте первую выше.</div>}</div>;
}

export function TariffPanel({ api, groups, onClose, onSaved }: { api: GameClubApi; groups: BackendWorkstationGroup[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState("main");
  const [duration, setDuration] = useState("60");
  const [price, setPrice] = useState("300");
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
    if (!name.trim() || !Number.isInteger(durationMinutes) || durationMinutes <= 0 || !Number.isFinite(priceRubles) || priceRubles < 0) {
      setError("Заполните название, длительность и корректную цену");
      return;
    }
    const parsedDate = new Date(validFrom);
    if (Number.isNaN(parsedDate.getTime())) {
      setError("Укажите дату начала действия тарифа");
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
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать тариф");
    } finally {
      setSubmitting(false);
    }
  };

  const tariffGroups = groups.length ? groups : [{ id: "main", name: "Обычный зал" }, { id: "vip", name: "VIP-зона" }];
  return <div className="panel-inner"><div className="panel-header"><div><p>Настройки клуба</p><h2>Новый пакет времени</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Пакет 1 час" autoFocus /></label><label>Зона<select value={groupId} onChange={(event) => setGroupId(event.target.value)}>{tariffGroups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label><label>Длительность, минут<input type="number" min="1" step="1" value={duration} onChange={(event) => setDuration(event.target.value)} /></label><label>Цена пакета, ₽<input type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label><label>Начало действия<DateTimePicker value={validFrom} onChange={setValidFrom} mode="datetime" label="Начало действия тарифа" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Создать draft-тариф"}</button><p className="subheading">Поминутная ставка и бесплатные минуты настраиваются в карточке зоны, а здесь создаются только пакеты времени.</p></form></div>;
}

export function ProductPanel({ api, product, onClose, onSaved }: { api: GameClubApi; product?: BackendProduct; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState(product?.category ?? "");
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [price, setPrice] = useState(product ? String(product.price_cents / 100) : "0");
  const [costPrice, setCostPrice] = useState(product ? String(product.cost_price_cents / 100) : "0");
  const [stock, setStock] = useState(product ? String(product.stock_quantity) : "0");
  const [active, setActive] = useState(product?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void api.listProductCategories().then((items) => {
      setCategories(items);
      setCategory((current) => current || items[0]?.id || "");
    }).catch(() => setCategories([]));
  }, [api]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const priceRubles = Number(price.replace(",", "."));
    const costRubles = Number(costPrice.replace(",", "."));
    const stockQuantity = Number(stock);
    if (!name.trim() || !category.trim() || !Number.isFinite(priceRubles) || priceRubles < 0 || !Number.isFinite(costRubles) || costRubles < 0 || !Number.isInteger(stockQuantity) || stockQuantity < 0) {
      setError("Заполните позицию, категорию, цены и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { name: name.trim(), category: category.trim(), price_cents: Math.round(priceRubles * 100), cost_price_cents: Math.round(costRubles * 100), stock_quantity: stockQuantity, active };
      if (product) await api.updateProduct(product.id, payload);
      else await api.createProduct(payload);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить товар");
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
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить товар");
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title={product ? "Редактирование товара" : "Новый товар"} subtitle="Каталог · позиция" onClose={onClose} /><form className="booking-form product-edit-form" onSubmit={(event) => void submit(event)}><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Кофе" autoFocus /></label><label>Категория<select value={category} onChange={(event) => setCategory(event.target.value)} disabled={!categories.length}><option value="">{categories.length ? "Выберите категорию" : "Сначала создайте категорию"}</option>{categories.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.kind === "drink" ? "напитки" : "товары"}</option>)}</select></label><div className="form-grid-two"><label>Цена продажи, ₽<input type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label><label>Закупочная цена, ₽<input type="number" min="0" step="0.01" value={costPrice} onChange={(event) => setCostPrice(event.target.value)} /></label></div><div className="form-grid-two"><label>Остаток, шт.<input type="number" min="0" step="1" value={stock} onChange={(event) => setStock(event.target.value)} /></label><label className="checkbox-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Позиция активна</label></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !categories.length}>{submitting ? "Сохраняем..." : product ? "Сохранить изменения" : "Создать товар"}</button></form>{product && <button className="danger-button product-delete-button" onClick={() => void remove()} disabled={submitting}>Удалить товар <ChevronRight size={15} /></button>}</div>;
}

export function DiscountPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
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
    if (!category.trim() || !Number.isFinite(percentValue) || percentValue < 0 || percentValue > 100 || !Number.isInteger(priorityValue) || priorityValue < 0 || Number.isNaN(parsedDate.getTime())) {
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
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать правило скидки");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><div className="panel-header"><div><p>Каталог</p><h2>Новая скидка</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}><label>Категория клиента<input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="student" autoFocus /></label><label>Скидка, %<input type="number" min="0" max="100" step="0.01" value={percent} onChange={(event) => setPercent(event.target.value)} /></label><label>Приоритет<input type="number" min="0" step="1" value={priority} onChange={(event) => setPriority(event.target.value)} /></label><label>Начало действия<DateTimePicker value={validFrom} onChange={setValidFrom} mode="datetime" label="Начало действия правила" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Создать правило"}</button><p className="subheading">При продаже будет использована самая приоритетная подходящая скидка.</p></form></div>;
}
