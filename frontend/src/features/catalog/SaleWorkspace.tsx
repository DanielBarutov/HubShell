import { useEffect, useRef, useState } from "react";
import { ArrowRightLeft, Check, ChevronRight, Clock3, Gamepad2, Minus, Plus, Receipt, Search, ShoppingCart, Sparkles, Tags, UserRound, WalletCards, X, UserX } from "lucide-react";
import { ApiError, GameClubApi, normalizePhoneQuery } from "../../api";
import type { BackendCashShift, BackendProduct, BackendProductCategory, BackendTariff } from "../../api";
import { toUiClient } from "../../adapters";
import { formatRussianPhone, getSearchField } from "../../shared/formatters";
import type { Client, Workstation } from "../../types";

type SaleLine = {
  key: string;
  kind: "tariff" | "product";
  sourceId: string;
  name: string;
  detail: string;
  priceCents: number;
  quantity: number;
  durationMinutes?: number;
  stockQuantity?: number;
};

const demoSaleTariffs: BackendTariff[] = [
  { id: "demo-tariff-3h", name: "Пакет 3 часа", group_id: null, duration_minutes: 180, price_cents: 32000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-3h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "demo-tariff-1h", name: "Пакет 1 час", group_id: null, duration_minutes: 60, price_cents: 10000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-1h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "demo-tariff-2h", name: "Пакет 2 часа", group_id: null, duration_minutes: 120, price_cents: 22000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-2h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
];

const demoSaleProducts: BackendProduct[] = [
  { id: "demo-cola", name: "Coca-Cola", category: "drinks", price_cents: 18000, active: true, cost_price_cents: 9000, stock_quantity: 12 },
  { id: "demo-coffee", name: "Кофе", category: "drinks", price_cents: 15000, active: true, cost_price_cents: 5500, stock_quantity: 24 },
  { id: "demo-water", name: "Вода 0,5 л", category: "drinks", price_cents: 10000, active: true, cost_price_cents: 4000, stock_quantity: 30 },
  { id: "demo-chips", name: "Чипсы Lay's", category: "snacks", price_cents: 22000, active: true, cost_price_cents: 12000, stock_quantity: 8 },
  { id: "demo-energy", name: "Monster", category: "energy", price_cents: 25000, active: true, cost_price_cents: 14000, stock_quantity: 6 },
  { id: "demo-headset", name: "Игровые наушники", category: "accessories", price_cents: 45000, active: true, cost_price_cents: 29000, stock_quantity: 3 },
];

export function SaleWorkspace({ api, pc, initialClient, initialProduct, clients: clientList, cashShifts, tariffs: catalogTariffs, products: catalogProducts, categories: catalogCategories, onClose, onSaved }: { api?: GameClubApi; pc: Workstation | null; initialClient: Client | null; initialProduct: BackendProduct | null; clients: Client[]; cashShifts: BackendCashShift[]; tariffs: BackendTariff[]; products: BackendProduct[]; categories: BackendProductCategory[]; onClose: () => void; onSaved: () => void }) {
  const [activeTab, setActiveTab] = useState<"time" | "products">("time");
  const [tariffCategory, setTariffCategory] = useState<"all" | "blocks">("all");
  const [productCategory, setProductCategory] = useState("all");
  const [lines, setLines] = useState<SaleLine[]>([]);
  const [buyerMode, setBuyerMode] = useState<"guest" | "client">("guest");
  const [clientQuery, setClientQuery] = useState("");
  const [client, setClient] = useState<Client | null>(null);
  const [availableTariffs, setAvailableTariffs] = useState<BackendTariff[] | null>(null);
  const [searchResults, setSearchResults] = useState<Client[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<"balance" | "cash" | "transfer" | "mixed">("cash");
  const [balancePartAmount, setBalancePartAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const seededProduct = useRef(false);
  const sessionIdempotencyKey = useRef(`sale-session-${crypto.randomUUID()}`);
  const tariffIdempotencyKeys = useRef(new Map<string, string[]>());
  const productIdempotencyKeys = useRef(new Map<string, string>());
  const [startedSession, setStartedSession] = useState<{ id: string; signature: string } | null>(null);
  const activeShift = cashShifts.find((shift) => shift.status === "open");
  const searchField = getSearchField(clientQuery);

  const categories = api ? catalogCategories : [
    { id: "drinks", name: "Напитки", kind: "drink" as const, active: true },
    { id: "snacks", name: "Снэки", kind: "product" as const, active: true },
    { id: "energy", name: "Энергетики", kind: "drink" as const, active: true },
    { id: "accessories", name: "Аксессуары", kind: "product" as const, active: true },
  ];
  const products = (api ? catalogProducts : demoSaleProducts).filter((item) => item.active && item.stock_quantity > 0);
  const workstationGroupId = pc?.groupId?.trim().toLowerCase();
  const sourceTariffs = availableTariffs ?? (api ? catalogTariffs : demoSaleTariffs);
  const tariffs = sourceTariffs.filter((item) => Boolean(workstationGroupId) && item.lifecycle === "published" && item.active && item.billing_mode === "block" && (item.group_id === null || item.group_id.trim().toLowerCase() === workstationGroupId));

  useEffect(() => {
    if (!api || !pc || typeof api.listAvailableTariffs !== "function") {
      setAvailableTariffs(null);
      return;
    }
    let cancelled = false;
    void api.listAvailableTariffs(pc.groupId ?? null, buyerMode === "guest" ? "guest" : "registered")
      .then((items) => {
        if (!cancelled) setAvailableTariffs(items);
      })
      .catch(() => {
        if (!cancelled) setAvailableTariffs([]);
      });
    return () => {
      cancelled = true;
    };
  }, [api, buyerMode, pc]);

  useEffect(() => {
    if (!initialClient) return;
    setClient(initialClient);
    setBuyerMode("client");
    setClientQuery(initialClient.nickname);
    setSearchResults([]);
  }, [initialClient?.id]);

  useEffect(() => {
    if (!initialProduct || seededProduct.current || !products.length) return;
    const product = products.find((item) => item.id === initialProduct.id);
    if (product) {
      setLines([{ key: `product:${product.id}`, kind: "product", sourceId: product.id, name: product.name, detail: "Товар", priceCents: product.price_cents, quantity: 1, stockQuantity: product.stock_quantity }]);
      setActiveTab("products");
      seededProduct.current = true;
    }
  }, [initialProduct, products]);

  useEffect(() => {
    if (!searchField) {
      setSearchResults([]);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      if (!api) {
        const normalized = clientQuery.trim().toLowerCase();
        const phoneQuery = normalizePhoneQuery(clientQuery);
        setSearchResults(clientList.filter((item) => searchField === "phone"
          ? normalizePhoneQuery(item.phone).includes(phoneQuery)
          : item.nickname.toLowerCase().includes(normalized)).slice(0, 4));
        return;
      }
      void api.searchClients(clientQuery, searchField).then((items) => {
        if (active) setSearchResults(items.map(toUiClient).slice(0, 4));
      }).catch(() => {
        if (active) setSearchResults([]);
      });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientList, clientQuery, searchField]);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? id;
  const formatDuration = (minutes: number) => minutes >= 60 ? `${minutes / 60} ч` : `${minutes} мин`;
  const timeLines = lines.filter((line) => line.kind === "tariff");
  const productLines = lines.filter((line) => line.kind === "product");
  const totalCents = lines.reduce((sum, line) => sum + line.priceCents * line.quantity, 0);
  const timeTotalCents = timeLines.reduce((sum, line) => sum + line.priceCents * line.quantity, 0);
  const productTotalCents = productLines.reduce((sum, line) => sum + line.priceCents * line.quantity, 0);
  const totalMinutes = timeLines.reduce((sum, line) => sum + (line.durationMinutes ?? 0) * line.quantity, 0);
  const mixedTariffs = new Set(timeLines.map((line) => line.sourceId)).size > 1;
  const activeClientSession = Boolean(
    pc?.status === "busy"
    && pc.clientId
    && client?.id === pc.clientId,
  );
  const lineCount = lines.reduce((sum, line) => sum + line.quantity, 0);
  const visibleTariffs = tariffCategory === "all" ? tariffs : tariffs.filter((tariff) => tariff.billing_mode === "block");
  const productCategoryOptions = ["all", ...Array.from(new Set(products.map((product) => product.category)))];
  const visibleProducts = productCategory === "all" ? products : products.filter((product) => product.category === productCategory);

  const addTariff = (tariff: BackendTariff) => {
    setError(null);
    setSuccess(null);
    if (activeClientSession) setPaymentMethod("balance");
    setLines((current) => {
      const key = `tariff:${tariff.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing) return current.map((line) => line.key === key ? { ...line, quantity: Math.min(10, line.quantity + 1) } : line);
      return [...current, { key, kind: "tariff", sourceId: tariff.id, name: tariff.name, detail: formatDuration(tariff.duration_minutes), priceCents: tariff.price_cents, quantity: 1, durationMinutes: tariff.duration_minutes }];
    });
  };
  const addProduct = (product: BackendProduct) => {
    setError(null);
    setSuccess(null);
    setLines((current) => {
      const key = `product:${product.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing) return current.map((line) => line.key === key ? { ...line, quantity: Math.min(product.stock_quantity, line.quantity + 1) } : line);
      return [...current, { key, kind: "product", sourceId: product.id, name: product.name, detail: categoryName(product.category), priceCents: product.price_cents, quantity: 1, stockQuantity: product.stock_quantity }];
    });
  };
  const changeQuantity = (key: string, delta: number) => setLines((current) => current.flatMap((line) => {
    if (line.key !== key) return [line];
    const max = line.kind === "product" ? line.stockQuantity ?? 1 : 10;
    const quantity = Math.min(max, line.quantity + delta);
    return quantity > 0 ? [{ ...line, quantity }] : [];
  }));
  const removeLine = (key: string) => setLines((current) => current.filter((line) => line.key !== key));
  const selectClient = (value: Client) => {
    setClient(value);
    setBuyerMode("client");
    setClientQuery(value.nickname);
    setSearchResults([]);
    setError(null);
  };
  const selectGuest = () => {
    setBuyerMode("guest");
    setClient(null);
    setClientQuery("");
    setSearchResults([]);
    if (paymentMethod === "balance" || paymentMethod === "mixed") setPaymentMethod("cash");
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (!lines.length) {
      setError("Добавьте в продажу хотя бы одну позицию");
      return;
    }
    if (mixedTariffs) {
      setError("Разные пакеты времени оформляются отдельно. Корзина сохранена.");
      return;
    }
    if (timeLines.length && !pc) {
      setError("Продажа времени доступна из карточки игрового места");
      return;
    }
    if (timeLines.length && pc && pc.status === "busy" && !activeClientSession) {
      setError("Тариф можно добавить только в активную сессию зарегистрированного клиента этого места. Товары можно оформить отдельно.");
      return;
    }
    if (timeLines.length && pc && pc.status !== "online" && !activeClientSession) {
      setError("Новую сессию нельзя открыть: игровое место не в сети");
      return;
    }
    if ((paymentMethod === "balance" || paymentMethod === "mixed") && !client) {
      setError("Для оплаты с баланса выберите зарегистрированного клиента");
      return;
    }
    if (activeClientSession && timeLines.length && paymentMethod !== "balance") {
      setError("Тариф для активной поминутной сессии покупается с депозита клиента. Пополните депозит или выберите оплату «Баланс».");
      return;
    }
    if (api && (paymentMethod === "cash" || paymentMethod === "mixed") && !activeShift) {
      setError("Нет актуальной открытой кассовой смены");
      return;
    }
    const balancePartCents = Math.round(Number(balancePartAmount.replace(",", ".")) * 100);
    if (paymentMethod === "mixed" && (
      productLines.length !== 1
      || !Number.isInteger(balancePartCents)
      || balancePartCents <= 0
      || balancePartCents >= productTotalCents
    )) {
      setError("Для смешанной оплаты выберите один товар и укажите часть с баланса меньше его суммы");
      return;
    }
    if (api && buyerMode === "guest" && timeLines.length) {
      if ((paymentMethod === "cash" || paymentMethod === "mixed") && !activeShift) {
        setError("Для гостевого тарифа нужна открытая кассовая смена");
        return;
      }
      if (timeTotalCents <= 0) {
        setError("Гостевой прямой оплатой можно провести только тариф с фиксированной ценой");
        return;
      }
    }
    const timeSignature = timeLines[0] ? `${timeLines[0].sourceId}:${timeLines[0].quantity}` : "";
    if (startedSession && startedSession.signature !== timeSignature) {
      setError("Сессия уже запущена с другим тарифом. Завершите текущую операцию или откройте новую продажу.");
      return;
    }
    setSubmitting(true);
    try {
      if (!api) {
        setSuccess("Демо: заказ собран и готов к проведению");
        return;
      }
      let guestPaymentId: string | undefined;
      if (buyerMode === "guest" && timeLines[0] && !startedSession) {
        const payment = await api.confirmGuestSessionPayment(
          {
            workstation_id: pc!.id,
            tariff_id: timeLines[0].sourceId,
            tariff_quantity: timeLines[0].quantity,
            guest_name: "Гость",
            cash_shift_id: paymentMethod === "cash" ? activeShift?.id : undefined,
            payment_parts: [{ method: paymentMethod, amount_cents: timeTotalCents }],
          },
          `guest-payment-${sessionIdempotencyKey.current}`,
        );
        if (payment.status !== "confirmed") {
          setError(
            payment.status === "needs_review"
              ? "Оплата гостя требует ручной сверки; сессия не запущена"
              : "Оплата гостя ещё не подтверждена; сессия не запущена",
          );
          return;
        }
        guestPaymentId = payment.id;
      }
      if (pc && timeLines[0] && !startedSession) {
        if (activeClientSession) {
          const tariffLine = timeLines[0];
          const purchaseKeys = tariffIdempotencyKeys.current.get(tariffLine.key) ?? [];
          for (let index = purchaseKeys.length; index < tariffLine.quantity; index += 1) {
            purchaseKeys.push(`sale-tariff-${crypto.randomUUID()}`);
          }
          tariffIdempotencyKeys.current.set(tariffLine.key, purchaseKeys);
          for (const purchaseKey of purchaseKeys.slice(0, tariffLine.quantity)) {
            await api.purchaseEntitlement(client!.id, tariffLine.sourceId, purchaseKey);
          }
        } else {
          const session = await api.startSession({
              workstation_id: pc.id,
              client_id: client?.id,
              guest_name: client ? undefined : "Гость",
              guest_payment_id: guestPaymentId,
              source: "operator",
              tariff_id: timeLines[0].sourceId,
              tariff_quantity: timeLines[0].quantity,
            }, sessionIdempotencyKey.current);
          setStartedSession({ id: session.id, signature: timeSignature });
        }
      }
      for (const line of productLines) {
        const operationKey = productIdempotencyKeys.current.get(line.key) ?? `sale-product-${crypto.randomUUID()}`;
        productIdempotencyKeys.current.set(line.key, operationKey);
          const lineTotalCents = line.priceCents * line.quantity;
          const lineBalanceCents = paymentMethod === "mixed" ? balancePartCents : 0;
          const linePaymentParts = paymentMethod === "mixed"
            ? [
              { method: "balance", amount_cents: lineBalanceCents },
              { method: "cash", amount_cents: lineTotalCents - lineBalanceCents },
            ]
            : paymentMethod === "transfer"
              ? [{ method: "transfer", amount_cents: lineTotalCents }]
              : undefined;
          const sale = await api.sellProduct({
            product_id: line.sourceId,
            quantity: line.quantity,
            client_id: client?.id,
            payment_method: paymentMethod,
            cash_shift_id: paymentMethod === "cash" || paymentMethod === "mixed" ? activeShift?.id : undefined,
            payment_parts: linePaymentParts,
          }, operationKey);
          if (sale.status !== "completed") {
            setError(
              sale.status === "needs_review"
                ? `Продажа сохранена для ручной сверки: ${sale.settlement_error ?? "неизвестный результат settlement"}`
                : "Продажа сохранена в ожидании подтверждения settlement; повторная отправка заблокирована",
            );
            return;
          }
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось провести продажу");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="sale-workspace-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="sale-workspace" role="dialog" aria-modal="true" aria-labelledby="sale-workspace-title" onMouseDown={(event) => event.stopPropagation()}>
      <header className="sale-workspace-header">
        <div className="sale-workspace-title"><button type="button" className="sale-close-button" aria-label="Закрыть продажу" onClick={onClose}><X size={19} /></button><div><p>ОПЕРАЦИЯ · НОВАЯ ПРОДАЖА</p><h1 id="sale-workspace-title">Продажа для {pc?.name ?? "магазина"}</h1><span>{pc ? `${pc.group} · ${pc.status === "online" ? "готов к запуску" : "карточка места"}` : "Товары без привязки к игровому месту"}</span></div></div>
        <div className="sale-header-meta"><div className="sale-shift-badge"><i /><div><small>Актуальная смена</small><strong>{activeShift?.register_id ?? (api ? "Не открыта" : "Демо-смена")}</strong></div></div><div className="sale-header-total"><small>Итого</small><strong>{money(totalCents)}</strong></div></div>
      </header>
      <div className="sale-workspace-body">
        <div className="sale-workspace-main">
          <section className="sale-buyer-card">
            <div className="sale-section-heading"><div><span className="sale-step">01</span><div><h2>Покупатель</h2><p>Кому оформить время и товары</p></div></div>{buyerMode === "guest" && <span className="sale-auto-note"><Sparkles size={14} /> Гость включён автоматически</span>}</div>
            <div className="sale-buyer-choices"><button type="button" className={`sale-buyer-choice ${buyerMode === "guest" ? "selected" : ""}`} onClick={selectGuest}><span className="sale-choice-icon guest"><UserX size={17} /></span><span><strong>Гость</strong><small>Без регистрации и баланса</small></span>{buyerMode === "guest" && <Check size={16} />}</button><button type="button" className={`sale-buyer-choice ${buyerMode === "client" ? "selected" : ""}`} onClick={() => setBuyerMode("client")}><span className="sale-choice-icon client"><UserRound size={17} /></span><span><strong>{client?.nickname ?? "Зарегистрированный клиент"}</strong><small>{client ? `Баланс ${client.balance.toLocaleString("ru-RU")} ₽ · ${client.category}` : "Поиск по нику или телефону"}</small></span>{buyerMode === "client" && <Check size={16} />}</button></div>
            {buyerMode === "client" && <div className="sale-client-search"><Search size={17} /><input aria-label="Клиент для продажи" autoFocus value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClient(null); }} placeholder="Введите от 3 букв ника или 4 цифр телефона" />{client && <button type="button" className="sale-clear-client" aria-label="Сбросить клиента" onClick={() => { setClient(null); setClientQuery(""); }}>×</button>}</div>}
            {buyerMode === "client" && searchResults.length > 0 && !client && <div className="sale-client-results">{searchResults.map((item) => <button type="button" className="sale-client-result" key={item.id} onClick={() => selectClient(item)}><span className="client-avatar">{item.nickname.slice(0, 2).toUpperCase()}</span><span><strong>{item.nickname}</strong><small>{formatRussianPhone(item.phone)} · баланс {item.balance.toLocaleString("ru-RU")} ₽</small></span><ChevronRight size={16} /></button>)}</div>}
          </section>
          <section className="sale-catalog-card">
            <div className="sale-section-heading"><div><span className="sale-step">02</span><div><h2>Добавьте в продажу</h2><p>Выберите несколько позиций — они появятся справа в заказе</p></div></div><div className="sale-catalog-count"><span>{lineCount}</span> поз. в заказе</div></div>
            <div className="sale-main-tabs" role="tablist" aria-label="Каталог продажи"><button type="button" className={activeTab === "time" ? "selected" : ""} role="tab" aria-selected={activeTab === "time"} onClick={() => setActiveTab("time")}><Clock3 size={16} /> Игровое время <em>{tariffs.length}</em></button><button type="button" className={activeTab === "products" ? "selected" : ""} role="tab" aria-selected={activeTab === "products"} onClick={() => setActiveTab("products")}><ShoppingCart size={16} /> Товары и напитки <em>{products.length}</em></button></div>
            {activeTab === "time" ? <><div className="sale-category-tabs"><button type="button" className={tariffCategory === "all" ? "selected" : ""} onClick={() => setTariffCategory("all")}>Все пакеты</button><button type="button" className={tariffCategory === "blocks" ? "selected" : ""} onClick={() => setTariffCategory("blocks")}><Tags size={14} /> Пакеты времени</button></div><div className="sale-item-grid">{visibleTariffs.map((tariff) => <button type="button" className="sale-item-card time-card" key={tariff.id} onClick={() => addTariff(tariff)}><div className="sale-item-top"><span className="sale-item-icon package"><Gamepad2 size={18} /></span><span className="sale-add-icon"><Plus size={16} /></span></div><strong>{tariff.name}</strong><small>{formatDuration(tariff.duration_minutes)} игрового времени</small><div className="sale-item-price"><b>{money(tariff.price_cents)}</b><span>за пакет</span></div></button>)}{!visibleTariffs.length && <div className="sale-empty-catalog">Опубликованных пакетов нет</div>}</div></> : <><div className="sale-category-tabs">{productCategoryOptions.map((category) => <button type="button" className={productCategory === category ? "selected" : ""} key={category} onClick={() => setProductCategory(category)}>{category === "all" ? "Все товары" : categoryName(category)}</button>)}</div><div className="sale-item-grid">{visibleProducts.map((product) => <button type="button" className="sale-item-card product-card" key={product.id} onClick={() => addProduct(product)}><div className="sale-item-top"><span className="sale-item-icon product"><ShoppingCart size={18} /></span><span className="sale-stock">{product.stock_quantity} шт.</span></div><strong>{product.name}</strong><small>{categoryName(product.category)}</small><div className="sale-item-price"><b>{money(product.price_cents)}</b><span>за штуку</span></div></button>)}{!visibleProducts.length && <div className="sale-empty-catalog">Товаров с остатком нет</div>}</div></>}
          </section>
        </div>
        <form className="sale-order-panel" onSubmit={(event) => void submit(event)}>
          <div className="sale-order-heading"><div><span className="sale-step">03</span><div><h2>Заказ</h2><p>{client?.nickname ?? "Гость"} · {pc?.name ?? "без ПК"}</p></div></div><span className="sale-order-count">{lineCount}</span></div>
          <div className="sale-order-target"><span className="sale-target-icon"><Gamepad2 size={17} /></span><div><small>Игровое место</small><strong>{pc?.name ?? "Не выбрано"}</strong></div><span className={`sale-target-status ${pc ? "ready" : "muted"}`}>{pc ? "Готово" : "Только товары"}</span></div>
          <div className="sale-lines">{lines.length ? lines.map((line) => <div className="sale-line" key={line.key}><div className={`sale-line-icon ${line.kind}`}>
            {line.kind === "tariff" ? <Clock3 size={15} /> : <ShoppingCart size={15} />}
          </div><div className="sale-line-info"><strong>{line.name}</strong><small>{line.detail}</small><b>{money(line.priceCents * line.quantity)}</b></div><div className="sale-quantity"><button type="button" aria-label={`Уменьшить ${line.name}`} onClick={() => changeQuantity(line.key, -1)}><Minus size={13} /></button><span>{line.quantity}</span><button type="button" aria-label={`Увеличить ${line.name}`} onClick={() => changeQuantity(line.key, 1)}><Plus size={13} /></button></div><button type="button" className="sale-remove-line" aria-label={`Удалить ${line.name}`} onClick={() => removeLine(line.key)}><X size={14} /></button></div>) : <div className="sale-empty-order"><Receipt size={24} /><strong>Заказ пока пуст</strong><span>Нажимайте на карточки слева, чтобы добавить время или товары</span></div>}</div>
          <div className="sale-order-summary"><div><span>Игровое время</span><strong>{totalMinutes ? formatDuration(totalMinutes) : "—"}</strong></div><div><span>Товары</span><strong>{productLines.length ? `${productLines.reduce((sum, line) => sum + line.quantity, 0)} шт.` : "—"}</strong></div><div className="sale-total-row"><span>Итого к оплате</span><strong>{money(totalCents)}</strong></div></div>
          {mixedTariffs && <div className="sale-inline-warning"><Tags size={16} /><span>В корзине разные пакеты времени. Оформите их отдельными покупками.</span></div>}
          <div className="sale-payment"><div className="sale-payment-heading"><span>{activeClientSession && timeLines.length ? "Оплата тарифа с депозита клиента" : "Способ оплаты товаров и гостевого времени"}</span></div><div className="sale-payment-tabs"><button type="button" className={paymentMethod === "cash" ? "selected" : ""} onClick={() => setPaymentMethod("cash")} disabled={Boolean(activeClientSession && timeLines.length)}><Receipt size={15} /> Наличные</button><button type="button" className={paymentMethod === "transfer" ? "selected" : ""} onClick={() => setPaymentMethod("transfer")} disabled={Boolean(activeClientSession && timeLines.length)}><ArrowRightLeft size={15} /> Перевод</button><button type="button" className={paymentMethod === "balance" ? "selected" : ""} disabled={!client} onClick={() => setPaymentMethod("balance")}><WalletCards size={15} /> Баланс</button><button type="button" className={paymentMethod === "mixed" ? "selected" : ""} disabled={!client || productLines.length !== 1 || Boolean(activeClientSession && timeLines.length)} onClick={() => { setPaymentMethod("mixed"); if (!balancePartAmount) setBalancePartAmount((productTotalCents / 200).toFixed(2)); }}><Tags size={15} /> Смешанная</button></div>{activeClientSession && timeLines.length && <p className="sale-payment-hint">Пакет будет сразу подключён к текущей сессии и начнёт действовать после покупки.</p>}{paymentMethod === "mixed" && <label className="amount-field">С баланса<input inputMode="decimal" value={balancePartAmount} onChange={(event) => setBalancePartAmount(event.target.value)} /> <span>₽</span></label>}</div>
          {error && <div className="sale-form-error" role="alert">{error}</div>}
          {success && <div className="sale-form-success" role="status">{success}</div>}
          <button className="sale-submit-button" disabled={submitting || !lines.length || mixedTariffs}>{submitting ? "Проводим заказ…" : `Оформить продажу · ${money(totalCents)}`}<ChevronRight size={17} /></button>
          <button type="button" className="sale-cancel-button" onClick={onClose}>Отмена</button>
        </form>
      </div>
    </section>
  </div>;
}
