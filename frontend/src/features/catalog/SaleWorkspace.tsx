import { useEffect, useRef, useState } from "react";
import {
  ArrowRightLeft,
  ChevronRight,
  Clock3,
  Gamepad2,
  Minus,
  Plus,
  Receipt,
  Search,
  ShoppingCart,
  Sparkles,
  Tags,
  UserRound,
  WalletCards,
  X,
  UserX,
} from "lucide-react";
import { ApiError, GameClubApi, normalizePhoneQuery } from "../../api";
import type {
  BackendCashShift,
  BackendProduct,
  BackendProductCategory,
  BackendTariff,
  BackendBonusGameQuote,
  BonusPurchaseConfirmation,
} from "../../api";
import { BonusPackageConfirmation } from "./BonusPackageConfirmation";
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
  {
    id: "demo-tariff-3h",
    name: "Пакет 3 часа",
    group_id: null,
    duration_minutes: 180,
    price_cents: 32000,
    valid_from: "2026-01-01T00:00:00Z",
    valid_to: null,
    active: true,
    tariff_key: "demo-3h",
    version: 1,
    lifecycle: "published",
    billing_mode: "block",
    price_per_minute_cents: 0,
    free_minutes: 0,
  },
  {
    id: "demo-tariff-1h",
    name: "Пакет 1 час",
    group_id: null,
    duration_minutes: 60,
    price_cents: 10000,
    valid_from: "2026-01-01T00:00:00Z",
    valid_to: null,
    active: true,
    tariff_key: "demo-1h",
    version: 1,
    lifecycle: "published",
    billing_mode: "block",
    price_per_minute_cents: 0,
    free_minutes: 0,
  },
  {
    id: "demo-tariff-2h",
    name: "Пакет 2 часа",
    group_id: null,
    duration_minutes: 120,
    price_cents: 22000,
    valid_from: "2026-01-01T00:00:00Z",
    valid_to: null,
    active: true,
    tariff_key: "demo-2h",
    version: 1,
    lifecycle: "published",
    billing_mode: "block",
    price_per_minute_cents: 0,
    free_minutes: 0,
  },
];

const demoSaleProducts: BackendProduct[] = [
  {
    id: "demo-cola",
    name: "Coca-Cola",
    category: "drinks",
    price_cents: 18000,
    active: true,
    cost_price_cents: 9000,
    stock_quantity: 12,
  },
  {
    id: "demo-coffee",
    name: "Кофе",
    category: "drinks",
    price_cents: 15000,
    active: true,
    cost_price_cents: 5500,
    stock_quantity: 24,
  },
  {
    id: "demo-water",
    name: "Вода 0,5 л",
    category: "drinks",
    price_cents: 10000,
    active: true,
    cost_price_cents: 4000,
    stock_quantity: 30,
  },
  {
    id: "demo-chips",
    name: "Чипсы Lay's",
    category: "snacks",
    price_cents: 22000,
    active: true,
    cost_price_cents: 12000,
    stock_quantity: 8,
  },
  {
    id: "demo-energy",
    name: "Monster",
    category: "energy",
    price_cents: 25000,
    active: true,
    cost_price_cents: 14000,
    stock_quantity: 6,
  },
  {
    id: "demo-headset",
    name: "Игровые наушники",
    category: "accessories",
    price_cents: 45000,
    active: true,
    cost_price_cents: 29000,
    stock_quantity: 3,
  },
];

export function SaleWorkspace({
  api,
  pc,
  initialClient,
  initialProduct,
  initialTab = "time",
  clients: clientList,
  cashShifts,
  tariffs: catalogTariffs,
  products: catalogProducts,
  categories: catalogCategories,
  onClose,
  onSaved,
}: {
  api?: GameClubApi;
  pc: Workstation | null;
  initialClient: Client | null;
  initialProduct: BackendProduct | null;
  initialTab?: "time" | "products";
  clients: Client[];
  cashShifts: BackendCashShift[];
  tariffs: BackendTariff[];
  products: BackendProduct[];
  categories: BackendProductCategory[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isXbox = pc?.equipmentType === "xbox";
  const [activeTab, setActiveTab] = useState<"time" | "products">(initialTab);
  const [tariffCategory, setTariffCategory] = useState<"all" | "blocks">("all");
  const [productCategory, setProductCategory] = useState("all");
  const [lines, setLines] = useState<SaleLine[]>([]);
  const [buyerMode, setBuyerMode] = useState<"guest" | "client">(() =>
    !isXbox && (initialClient || (pc?.status === "busy" && pc.clientId))
      ? "client"
      : "guest",
  );
  const [clientQuery, setClientQuery] = useState("");
  const [client, setClient] = useState<Client | null>(null);
  const [availableTariffs, setAvailableTariffs] = useState<
    BackendTariff[] | null
  >(null);
  const [searchResults, setSearchResults] = useState<Client[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<
    "balance" | "cash" | "transfer" | "mixed"
  >("cash");
  const [cashPartAmount, setCashPartAmount] = useState("");
  const [transferPartAmount, setTransferPartAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [useBonus, setUseBonus] = useState(false);
  const [bonusConfirmation, setBonusConfirmation] = useState<{ quote: BackendBonusGameQuote; name: string; position: string } | null>(null);
  const resolveBonusConfirmation = useRef<((confirmed: boolean) => void) | null>(null);
  const confirmedBonusPurchases = useRef(new Map<string, BonusPurchaseConfirmation>());
  const completedTariffPurchases = useRef(new Set<string>());
  useEffect(() => () => { resolveBonusConfirmation.current?.(false); }, []);
  const finishBonusConfirmation = (confirmed: boolean) => {
    setBonusConfirmation(null);
    resolveBonusConfirmation.current?.(confirmed);
    resolveBonusConfirmation.current = null;
  };
  const seededProduct = useRef(false);
  const sessionIdempotencyKey = useRef(`sale-session-${crypto.randomUUID()}`);
  const tariffIdempotencyKeys = useRef(new Map<string, string[]>());
  const productIdempotencyKeys = useRef(new Map<string, string>());
  const activeShift = cashShifts.find((shift) => shift.status === "open");
  const searchField = getSearchField(clientQuery);

  const categories = api
    ? catalogCategories
    : [
        { id: "drinks", name: "Напитки", kind: "drink" as const, active: true },
        { id: "snacks", name: "Снэки", kind: "product" as const, active: true },
        {
          id: "energy",
          name: "Энергетики",
          kind: "drink" as const,
          active: true,
        },
        {
          id: "accessories",
          name: "Аксессуары",
          kind: "product" as const,
          active: true,
        },
      ];
  const products = (api ? catalogProducts : demoSaleProducts).filter(
    (item) => item.active && item.stock_quantity > 0,
  );
  const workstationGroupId =
    pc?.groupId?.trim().toLowerCase() ??
    (pc?.group === "VIP-зона"
      ? "vip"
      : pc?.group === "Обычный зал" || pc?.group === "Основной зал"
        ? "main"
        : undefined);
  const registeredSession = Boolean(pc?.status === "busy" && pc.clientId);
  const sourceTariffs =
    (isXbox ? null : availableTariffs) ?? (api ? catalogTariffs : demoSaleTariffs);
  const tariffs = sourceTariffs.filter(
    (item) =>
      (item.equipment_type ?? "pc") === (pc?.equipmentType ?? "pc") &&
      Boolean(pc) &&
      item.lifecycle === "published" &&
      item.active &&
      item.billing_mode === "block" &&
      (!workstationGroupId ||
        item.group_id === null ||
        item.group_id.trim().toLowerCase() === workstationGroupId),
  );

  useEffect(() => {
    if (isXbox || !api || !pc || typeof api.listAvailableTariffs !== "function") {
      setAvailableTariffs(null);
      return;
    }
    let cancelled = false;
    void api
      .listAvailableTariffs(
        pc.groupId ?? null,
        buyerMode === "guest" ? "guest" : "registered",
      )
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
    if (isXbox || !initialClient) return;
    setClient(initialClient);
    setBuyerMode("client");
    setClientQuery(initialClient.nickname);
    setSearchResults([]);
  }, [initialClient?.id, isXbox]);

  useEffect(() => {
    if (registeredSession && !initialClient) setBuyerMode("client");
  }, [initialClient, registeredSession]);

  useEffect(() => {
    if (!initialProduct || seededProduct.current || !products.length) return;
    const product = products.find((item) => item.id === initialProduct.id);
    if (product) {
      setLines([
        {
          key: `product:${product.id}`,
          kind: "product",
          sourceId: product.id,
          name: product.name,
          detail: "Товар",
          priceCents: product.price_cents,
          quantity: 1,
          stockQuantity: product.stock_quantity,
        },
      ]);
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
        setSearchResults(
          clientList
            .filter((item) =>
              searchField === "phone"
                ? normalizePhoneQuery(item.phone).includes(phoneQuery)
                : item.nickname.toLowerCase().includes(normalized),
            )
            .slice(0, 4),
        );
        return;
      }
      void api
        .searchClients(clientQuery, searchField)
        .then((items) => {
          if (active) setSearchResults(items.map(toUiClient).slice(0, 4));
        })
        .catch(() => {
          if (active) setSearchResults([]);
        });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientList, clientQuery, searchField]);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const categoryName = (id: string) =>
    categories.find((category) => category.id === id)?.name ?? id;
  const formatDuration = (minutes: number) =>
    minutes >= 60 ? `${minutes / 60} ч` : `${minutes} мин`;
  const timeLines = lines.filter((line) => line.kind === "tariff");
  const productLines = lines.filter((line) => line.kind === "product");
  const totalCents = lines.reduce(
    (sum, line) => sum + line.priceCents * line.quantity,
    0,
  );
  const timeTotalCents = timeLines.reduce(
    (sum, line) => sum + line.priceCents * line.quantity,
    0,
  );
  const productTotalCents = productLines.reduce(
    (sum, line) => sum + line.priceCents * line.quantity,
    0,
  );
  const totalMinutes = timeLines.reduce(
    (sum, line) => sum + (line.durationMinutes ?? 0) * line.quantity,
    0,
  );
  const mixedTariffs = new Set(timeLines.map((line) => line.sourceId)).size > 1;
  const activeClientSession = Boolean(
    registeredSession && client?.id === pc?.clientId,
  );
  const activeGuestSession = Boolean(
    pc?.status === "busy" && !pc.clientId && pc.sessionId && buyerMode === "guest",
  );
  const lineCount = lines.reduce((sum, line) => sum + line.quantity, 0);
  const visibleTariffs =
    tariffCategory === "all"
      ? tariffs
      : tariffs.filter((tariff) => tariff.billing_mode === "block");
  const productCategoryOptions = [
    "all",
    ...Array.from(new Set(products.map((product) => product.category))),
  ];
  const visibleProducts =
    productCategory === "all"
      ? products
      : products.filter((product) => product.category === productCategory);
  const mixedSaleSupported =
    (timeLines.length === 0 && productLines.length === 1) ||
    (timeLines.length === 1 &&
      productLines.length === 0 &&
      (buyerMode === "guest" || activeClientSession));

  const addTariff = (tariff: BackendTariff) => {
    setError(null);
    setSuccess(null);
    if (activeClientSession) setPaymentMethod("balance");
    setLines((current) => {
      const key = `tariff:${tariff.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing && isXbox) return current;
      if (existing)
        return current.map((line) =>
          line.key === key
            ? { ...line, quantity: Math.min(10, line.quantity + 1) }
            : line,
        );
      return [
        ...current,
        {
          key,
          kind: "tariff",
          sourceId: tariff.id,
          name: tariff.name,
          detail: formatDuration(tariff.duration_minutes),
          priceCents: tariff.price_cents,
          quantity: 1,
          durationMinutes: tariff.duration_minutes,
        },
      ];
    });
  };
  const addProduct = (product: BackendProduct) => {
    setError(null);
    setSuccess(null);
    setLines((current) => {
      const key = `product:${product.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing)
        return current.map((line) =>
          line.key === key
            ? {
                ...line,
                quantity: Math.min(product.stock_quantity, line.quantity + 1),
              }
            : line,
        );
      return [
        ...current,
        {
          key,
          kind: "product",
          sourceId: product.id,
          name: product.name,
          detail: categoryName(product.category),
          priceCents: product.price_cents,
          quantity: 1,
          stockQuantity: product.stock_quantity,
        },
      ];
    });
  };
  const changeQuantity = (key: string, delta: number) =>
    setLines((current) =>
      current.flatMap((line) => {
        if (line.key !== key) return [line];
        const max = line.kind === "product" ? (line.stockQuantity ?? 1) : isXbox ? 1 : 10;
        const quantity = Math.min(max, line.quantity + delta);
        return quantity > 0 ? [{ ...line, quantity }] : [];
      }),
    );
  const removeLine = (key: string) =>
    setLines((current) => current.filter((line) => line.key !== key));
  const selectClient = (value: Client) => {
    if (registeredSession && value.id !== pc?.clientId) {
      setError(
        "Для занятого места доступен только текущий зарегистрированный клиент",
      );
      return;
    }
    setClient(value);
    setBuyerMode("client");
    setClientQuery(value.nickname);
    setSearchResults([]);
    setError(null);
  };
  const selectGuest = () => {
    if (registeredSession) {
      setError(
        "На занятом месте нельзя оформить гостевой тариф поверх сессии клиента",
      );
      return;
    }
    setBuyerMode("guest");
    setClient(null);
    setClientQuery("");
    setSearchResults([]);
    if (paymentMethod === "balance" || paymentMethod === "mixed")
      setPaymentMethod("cash");
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
      setError(
        "Разные пакеты времени оформляются отдельно. Корзина сохранена.",
      );
      return;
    }
    if (timeLines.length && !pc) {
      setError("Продажа времени доступна из карточки игрового места");
      return;
    }
    if (
      timeLines.length &&
      pc &&
      pc.status === "busy" &&
      !activeClientSession &&
      !activeGuestSession
    ) {
      setError(
        "Для допродажи времени нужна текущая гостевая сессия или её зарегистрированный клиент. Товары можно оформить отдельно.",
      );
      return;
    }
    if (
      timeLines.length &&
      pc &&
      pc.status !== "online" &&
      !activeClientSession &&
      !activeGuestSession
    ) {
      setError("Новую сессию нельзя открыть: игровое место не в сети");
      return;
    }
    if (paymentMethod === "balance" && !client) {
      setError("Для оплаты с баланса выберите зарегистрированного клиента");
      return;
    }
    if (
      api &&
      (paymentMethod === "cash" || paymentMethod === "mixed") &&
      !activeShift
    ) {
      setError("Нет актуальной открытой кассовой смены");
      return;
    }
    const cashPartCents = Math.round(
      Number(cashPartAmount.replace(",", ".")) * 100,
    );
    const transferPartCents = Math.round(
      Number(transferPartAmount.replace(",", ".")) * 100,
    );
    const mixedTotalCents = timeLines.length
      ? timeTotalCents
      : productTotalCents;
    if (
      paymentMethod === "mixed" &&
      (!mixedSaleSupported ||
        !Number.isInteger(cashPartCents) ||
        !Number.isInteger(transferPartCents) ||
        cashPartCents <= 0 ||
        transferPartCents <= 0 ||
        cashPartCents + transferPartCents !== mixedTotalCents)
    ) {
      setError(
        "Для смешанной оплаты укажите положительные части наличными и переводом, равные сумме заказа",
      );
      return;
    }
    if (api && buyerMode === "guest" && timeLines.length) {
      if (
        (paymentMethod === "cash" || paymentMethod === "mixed") &&
        !activeShift
      ) {
        setError("Для гостевого тарифа нужна открытая кассовая смена");
        return;
      }
      if (timeTotalCents <= 0) {
        setError(
          "Гостевой прямой оплатой можно провести только тариф с фиксированной ценой",
        );
        return;
      }
    }
    setSubmitting(true);
    try {
      if (!api) {
        setSuccess("Демо: заказ собран и готов к проведению");
        return;
      }
      let guestAccessPrepared = false;
      if (buyerMode === "guest" && timeLines[0]) {
        if (isXbox && timeLines[0].quantity !== 1) {setError("Для Xbox выберите один тариф; повторная продажа продлевает сессию"); return;}
        const payment = await (isXbox ? api.confirmXboxSale.bind(api) : api.confirmGuestSessionPayment.bind(api))(
          {
            workstation_id: pc!.id,
            session_id: activeGuestSession ? pc!.sessionId : undefined,
            tariff_id: timeLines[0].sourceId,
            tariff_quantity: timeLines[0].quantity,
            guest_name: "Гость",
            cash_shift_id:
              paymentMethod === "cash" || paymentMethod === "mixed"
                ? activeShift?.id
                : undefined,
            payment_parts:
              paymentMethod === "mixed"
                ? [
                    { method: "cash", amount_cents: cashPartCents },
                    { method: "transfer", amount_cents: transferPartCents },
                  ]
                : [{ method: paymentMethod, amount_cents: timeTotalCents }],
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
        try {
          if (!isXbox) await api.prepareGuestSessionAccess(payment.id);
          guestAccessPrepared = true;
        } catch (accessError) {
          setError(
            accessError instanceof Error
              ? `Оплата подтверждена, но гостевой допуск не выдан: ${accessError.message}`
              : "Оплата подтверждена, но гостевой допуск не выдан",
          );
          return;
        }
      }
      if (pc && timeLines[0] && !guestAccessPrepared && client) {
        const tariffLine = timeLines[0];
        const purchaseKeys =
          tariffIdempotencyKeys.current.get(tariffLine.key) ?? [];
        for (
          let index = purchaseKeys.length;
          index < tariffLine.quantity;
          index += 1
        ) {
          purchaseKeys.push(`sale-tariff-${crypto.randomUUID()}`);
        }
        tariffIdempotencyKeys.current.set(tariffLine.key, purchaseKeys);
        let remainingCashPartCents =
          paymentMethod === "mixed" ? cashPartCents : 0;
        let remainingTransferPartCents =
          paymentMethod === "mixed" ? transferPartCents : 0;
        for (const purchaseKey of purchaseKeys.slice(0, tariffLine.quantity)) {
          if (completedTariffPurchases.current.has(purchaseKey)) continue;
          if ((useBonus && paymentMethod === "balance") || confirmedBonusPurchases.current.has(purchaseKey)) {
            let confirmation = confirmedBonusPurchases.current.get(purchaseKey);
            if (!confirmation) {
              const quote = await api.quoteEntitlement(client.id, tariffLine.sourceId, true);
              const confirmed = await new Promise<boolean>((resolve) => {
                resolveBonusConfirmation.current = resolve;
                setBonusConfirmation({ quote, name: tariffLine.name, position: `${purchaseKeys.indexOf(purchaseKey) + 1} из ${tariffLine.quantity}` });
              });
              if (!confirmed) {
                setError("Оставшаяся продажа отменена. Уже подтверждённые пакеты сохранены.");
                return;
              }
              confirmation = { use_bonus: true, expected_price_cents: quote.price_cents, expected_bonus_cents: quote.bonus_cents, expected_money_cents: quote.money_cents, expected_earned_bonus_cents: quote.earned_bonus_cents };
              confirmedBonusPurchases.current.set(purchaseKey, confirmation);
            }
            try {
              await api.purchaseEntitlement(client.id, tariffLine.sourceId, purchaseKey, undefined, undefined, confirmation);
              completedTariffPurchases.current.add(purchaseKey);
            } catch (purchaseError) {
              if (purchaseError instanceof ApiError && purchaseError.status === 409) confirmedBonusPurchases.current.delete(purchaseKey);
              throw purchaseError;
            }
            continue;
          }
          const unitCashPartCents =
            paymentMethod === "mixed"
              ? Math.min(tariffLine.priceCents, remainingCashPartCents)
              : paymentMethod === "cash"
                ? tariffLine.priceCents
                : 0;
          const unitTransferPartCents =
            paymentMethod === "mixed"
              ? tariffLine.priceCents - unitCashPartCents
              : paymentMethod === "transfer"
                ? tariffLine.priceCents
                : 0;
          remainingCashPartCents -= unitCashPartCents;
          remainingTransferPartCents -= unitTransferPartCents;
          const paymentParts =
            paymentMethod === "mixed"
              ? [
                  ...(unitCashPartCents > 0
                    ? [{ method: "cash", amount_cents: unitCashPartCents }]
                    : []),
                  ...(unitTransferPartCents > 0
                    ? [
                        {
                          method: "transfer",
                          amount_cents: unitTransferPartCents,
                        },
                      ]
                    : []),
                ]
              : [
                  {
                    method: paymentMethod,
                    amount_cents: tariffLine.priceCents,
                  },
                ];
          await api.purchaseEntitlement(
            client.id,
            tariffLine.sourceId,
            purchaseKey,
            paymentParts,
            paymentMethod === "cash" || paymentMethod === "mixed"
              ? activeShift?.id
              : undefined,
          );
        }
      }
      for (const line of productLines) {
        const operationKey =
          productIdempotencyKeys.current.get(line.key) ??
          `sale-product-${crypto.randomUUID()}`;
        productIdempotencyKeys.current.set(line.key, operationKey);
        const lineTotalCents = line.priceCents * line.quantity;
        const lineCashCents = paymentMethod === "mixed" ? cashPartCents : 0;
        const lineTransferCents =
          paymentMethod === "mixed" ? transferPartCents : 0;
        const linePaymentParts =
          paymentMethod === "mixed"
            ? [
                { method: "cash", amount_cents: lineCashCents },
                { method: "transfer", amount_cents: lineTransferCents },
              ]
            : paymentMethod === "transfer"
              ? [{ method: "transfer", amount_cents: lineTotalCents }]
              : undefined;
        const sale = await api.sellProduct(
          {
            product_id: line.sourceId,
            quantity: line.quantity,
            client_id: client?.id,
            payment_method: paymentMethod,
            cash_shift_id:
              paymentMethod === "cash" || paymentMethod === "mixed"
                ? activeShift?.id
                : undefined,
            payment_parts: linePaymentParts,
          },
          operationKey,
        );
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
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось провести продажу",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="sale-workspace-backdrop fixed inset-0 z-50 bg-black/60 p-4 [&_.sale-category-tabs]:border-primary/20! [&_.sale-category-tabs]:bg-base-100/70! [&_.sale-item-card]:border-primary/15! [&_.sale-item-card]:bg-base-100/70! [&_.sale-main-tabs]:border-primary/20! [&_.sale-main-tabs]:bg-base-100/70! [&_.sale-order-target]:border [&_.sale-order-target]:border-primary/15! [&_.sale-order-target]:bg-base-100/70! [&_.sale-line]:border-primary/15! [&_.sale-line]:bg-base-100/70! [&_.sale-empty-order]:border-primary/15! [&_.sale-empty-catalog]:border-primary/15! [&_.sale-order-summary]:border-primary/20! [&_.sale-payment]:border-primary/20! [&_.sale-payment-tabs]:border-primary/20! [&_.sale-payment-tabs]:bg-base-100/70! [&_.sale-payment-hint]:mt-2 [&_.sale-payment-hint]:rounded-lg [&_.sale-payment-hint]:border [&_.sale-payment-hint]:border-primary/15! [&_.sale-payment-hint]:bg-base-200/55! [&_.sale-payment-hint]:p-2 [&_.sale-payment-hint]:text-xs [&_.sale-payment-hint]:text-base-content/60! [&_.sale-catalog-count]:text-xs [&_.sale-catalog-count]:text-base-content/60!"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        inert={submitting}
        className="sale-workspace relative mx-auto flex h-full max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-primary/30! bg-base-100/95! text-base-content! shadow-[0_0_32px_rgba(49,217,120,0.12),0_25px_80px_rgba(0,0,0,0.52)] backdrop-blur-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sale-workspace-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="sale-workspace-header flex items-center justify-between gap-4 border-b border-primary/20! bg-base-200/85! px-5 py-3">
          <div className="sale-workspace-title flex min-w-0 items-center gap-3">
            <button
              type="button"
              className="sale-close-button btn btn-ghost btn-circle btn-sm"
              aria-label="Закрыть продажу"
              onClick={onClose}
            >
              <X size={19} />
            </button>
            <div>
              <p className="text-xs text-base-content/40! uppercase">
                ОПЕРАЦИЯ · НОВАЯ ПРОДАЖА
              </p>
              <h1 id="sale-workspace-title" className="text-base-content/60">
                Продажа для {pc?.name ?? "магазина"}
              </h1>
              <span className="text-xs text-base-content/40!">
                {pc
                  ? `${pc.group} · ${pc.status === "online" ? "готов к запуску" : "карточка места"}`
                  : "Товары без привязки к игровому месту"}
              </span>
            </div>
          </div>
          <div className="sale-header-meta flex items-center gap-3 text-xs text-base-content/60!">
            <div className="sale-shift-badge badge badge-soft badge-success flex h-auto items-center gap-2 py-2">
              <i className="size-1.5 rounded-full bg-current" />
              <div className="flex flex-col leading-tight">
                <small>Актуальная смена</small>
                <strong>
                  {activeShift?.register_id ??
                    (api ? "Не открыта" : "Демо-смена")}
                </strong>
              </div>
            </div>
            <div className="sale-header-total flex flex-col items-end text-lg font-bold leading-tight text-primary!">
              <small className="text-xs font-normal text-base-content/60!">
                Итого
              </small>
              <strong>{money(totalCents)}</strong>
            </div>
          </div>
        </header>
        <div className="sale-workspace-body grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="sale-workspace-main min-w-0 overflow-y-auto p-5">
            <section className="sale-buyer-card mb-4 rounded-xl border border-primary/15! bg-base-200/70! p-4">
              <div className="sale-section-heading mb-3 flex items-center justify-between gap-3">
                <div>
                  <span className="sale-step mb-2 inline-flex items-center badge badge-outline border-primary/30! text-primary!">
                    01
                  </span>
                  <div>
                    <h2>Покупатель</h2>
                    <p className="text-xs text-base-content/40!">
                      Кому оформить время и товары
                    </p>
                  </div>
                </div>
                {buyerMode === "guest" && (
                  <span className="sale-auto-note flex items-center gap-1 text-xs text-base-content/60!">
                    <Sparkles size={14} /> Гость включён автоматически
                  </span>
                )}
              </div>
              <div className="sale-buyer-choices grid grid-cols-1 gap-2 md:grid-cols-2">
                <button
                  type="button"
                  className={`sale-buyer-choice btn h-auto min-h-16 justify-start gap-3 text-left ${buyerMode === "guest" ? "bg-primary! text-primary-content!" : "btn-dash"}`}
                  onClick={selectGuest}
                  disabled={registeredSession}
                  aria-describedby={
                    registeredSession
                      ? "sale-registered-session-hint"
                      : undefined
                  }
                >
                  <span
                    className={`sale-choice-icon guest shrink-0 ${buyerMode === "guest" ? "text-primary-content!" : "text-primary!"}`}
                  >
                    <UserX size={17} />
                  </span>
                  <span className="flex min-w-0 flex-col items-start gap-0.5">
                    <strong className="block">Гость</strong>
                    <small className="block text-xs font-normal opacity-75">
                      Без регистрации и баланса
                    </small>
                  </span>
                </button>
                <button
                  hidden={isXbox}
                  type="button"
                  className={`sale-buyer-choice btn h-auto min-h-16 justify-start gap-3 text-left ${buyerMode === "client" ? "bg-primary! text-primary-content!" : "btn-dash"}`}
                  onClick={() => setBuyerMode("client")}
                >
                  <span
                    className={`sale-choice-icon client shrink-0 ${buyerMode === "client" ? "text-primary-content!" : "text-primary!"}`}
                  >
                    <UserRound size={17} />
                  </span>
                  <span className="flex min-w-0 flex-col items-start gap-0.5">
                    <strong className="block truncate">
                      {client?.nickname ?? "Зарегистрированный клиент"}
                    </strong>
                    <small className="block text-xs font-normal opacity-75">
                      {client
                        ? `Баланс ${client.balance.toLocaleString("ru-RU")} ₽ · ${client.category}`
                        : "Поиск по нику или телефону"}
                    </small>
                  </span>
                </button>
              </div>
              {registeredSession && (
                <p
                  id="sale-registered-session-hint"
                  className="sale-payment-hint"
                >
                  На занятом месте продажа времени доступна только текущему
                  зарегистрированному клиенту.
                </p>
              )}
              {buyerMode === "client" && (
                <div className="sale-client-search input input-sm mt-5 flex items-center gap-2">
                  <Search size={17} />
                  <input
                    className="input input-sm"
                    aria-label="Клиент для продажи"
                    autoFocus={!registeredSession}
                    value={clientQuery}
                    disabled={activeClientSession}
                    onChange={(event) => {
                      setClientQuery(event.target.value);
                      setClient(null);
                    }}
                    placeholder="Введите от 3 букв ника или 4 цифр телефона"
                  />
                  {client && !activeClientSession && (
                    <button
                      type="button"
                      className="sale-clear-client btn btn-ghost btn-circle btn-sm"
                      aria-label="Сбросить клиента"
                      onClick={() => {
                        setClient(null);
                        setClientQuery("");
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              )}
              {buyerMode === "client" &&
                searchResults.length > 0 &&
                !client && (
                  <div className="sale-client-results mt-2 flex flex-col gap-1">
                    {searchResults.map((item) => (
                      <button
                        type="button"
                        className="sale-client-result btn btn-dash py-7 flex w-full items-center justify-start gap-2"
                        key={item.id}
                        onClick={() => selectClient(item)}
                      >
                        <span className="client-avatar grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary! text-xs font-bold text-primary-content!">
                          {item.nickname.slice(0, 2).toUpperCase()}
                        </span>
                        <span className="min-w-0 text-left">
                          <strong className="block truncate">
                            {item.nickname}
                          </strong>
                          <small className="block truncate text-xs font-normal text-base-content/60!">
                            {formatRussianPhone(item.phone)} · баланс{" "}
                            {item.balance.toLocaleString("ru-RU")} ₽
                          </small>
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                )}
            </section>
            <section className="sale-catalog-card rounded-xl border border-primary/15! bg-base-200/70! p-4">
              <div className="sale-section-heading mb-3 flex items-center justify-between gap-3">
                <div>
                  <span className="sale-step mb-2 badge badge-outline border-primary/30! text-primary!">
                    02
                  </span>
                  <div>
                    <h2>Добавьте в продажу</h2>
                    <p className="text-xs text-base-content/40!">
                      Выберите несколько позиций — они появятся справа в заказе
                    </p>
                  </div>
                </div>
                <div className="sale-catalog-count">
                  <span>{lineCount}</span> поз. в заказе
                </div>
              </div>
              <div
                className="sale-main-tabs rounded-lg join mb-3 align-middle border border-primary/20! bg-base-100/70! p-1"
                role="tablist"
                aria-label="Каталог продажи"
              >
                <button
                  type="button"
                  className={`btn btn-sm ${activeTab === "time" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  role="tab"
                  aria-selected={activeTab === "time"}
                  onClick={() => setActiveTab("time")}
                >
                  <Clock3 size={16} /> Игровое время <em>{tariffs.length}</em>
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${activeTab === "products" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  role="tab"
                  aria-selected={activeTab === "products"}
                  onClick={() => setActiveTab("products")}
                >
                  <ShoppingCart size={16} /> Товары и напитки{" "}
                  <em>{products.length}</em>
                </button>
              </div>
              {activeTab === "time" ? (
                <>
                  <div className="sale-category-tabs rounded-lg join mb-3 ml-15 align-middle border border-primary/20! bg-base-100/70! p-1">
                    <button
                      type="button"
                      className={`btn btn-sm ${tariffCategory === "all" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
                      onClick={() => setTariffCategory("all")}
                    >
                      Все пакеты
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${tariffCategory === "blocks" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
                      onClick={() => setTariffCategory("blocks")}
                    >
                      <Tags size={14} /> Пакеты времени
                    </button>
                  </div>
                  <div className="sale-item-grid grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {visibleTariffs.map((tariff) => (
                      <button
                        type="button"
                        className="sale-item-card time-card btn btn-ghost h-auto flex-col items-stretch gap-2 rounded-xl border border-primary/20! bg-base-100/70! p-3 text-left"
                        key={tariff.id}
                        onClick={() => addTariff(tariff)}
                      >
                        <div className="sale-item-top flex items-center justify-between gap-2">
                          <span className="sale-item-icon package text-primary!">
                            <Gamepad2 size={18} />
                          </span>
                          <span className="sale-add-icon">
                            <Plus size={16} />
                          </span>
                        </div>
                        <strong>{tariff.name}</strong>
                        <small>
                          {formatDuration(tariff.duration_minutes)} игрового
                          времени
                        </small>
                        <div className="sale-item-price badge badge-lg text-lg font-bold text-primary!">
                          <b>{money(tariff.price_cents)}</b>
                        </div>
                      </button>
                    ))}
                    {!visibleTariffs.length && (
                      <div className="sale-empty-catalog rounded-lg border border-dashed border-primary/20! p-5 text-sm text-base-content/60!">
                        Опубликованных пакетов нет
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="sale-category-tabs rounded-lg join mb-3 ml-15 align-middle border border-primary/20! bg-base-100/70! p-1">
                    {productCategoryOptions.map((category) => (
                      <button
                        type="button"
                        className={`btn btn-sm ${productCategory === category ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
                        key={category}
                        onClick={() => setProductCategory(category)}
                      >
                        {category === "all"
                          ? "Все товары"
                          : categoryName(category)}
                      </button>
                    ))}
                  </div>
                  <div className="sale-item-grid product-item-grid grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {visibleProducts.map((product) => (
                      <button
                        type="button"
                        className="sale-item-card product-card btn btn-ghost h-auto flex-col items-stretch gap-2 rounded-xl border border-primary/20! bg-base-100/70! p-3 text-left"
                        key={product.id}
                        onClick={() => addProduct(product)}
                      >
                        <div className="sale-item-top flex items-center justify-between gap-2">
                          <span className="sale-item-icon product text-primary!">
                            <ShoppingCart size={18} />
                          </span>
                          <span className="sale-stock text-xs text-base-content/60!">
                            {product.stock_quantity} шт.
                          </span>
                        </div>
                        <strong>{product.name}</strong>
                        <small>{categoryName(product.category)}</small>
                        <div className="sale-item-price text-lg badge badge-lg font-bold text-primary!">
                          <b>{money(product.price_cents)}</b>
                        </div>
                      </button>
                    ))}
                    {!visibleProducts.length && (
                      <div className="sale-empty-catalog rounded-lg border border-dashed border-primary/20! p-5 text-sm text-base-content/60!">
                        Товаров с остатком нет
                      </div>
                    )}
                  </div>
                </>
              )}
            </section>
          </div>
          <form
            className="sale-order-panel min-w-0 overflow-y-auto border-t border-primary/20! bg-base-200/80! p-5 lg:border-l lg:border-t-0"
            onSubmit={(event) => void submit(event)}
          >
            <div className="sale-order-heading mb-3 flex items-center justify-between gap-3">
              <div>
                <span className="sale-step mb-2 badge badge-outline border-primary/30! text-primary!">
                  03
                </span>
                <div>
                  <h2>Заказ</h2>
                  <p className="text-xs text-base-content/40!">
                    {client?.nickname ?? "Гость"} · {pc?.name ?? "без ПК"}
                  </p>
                </div>
              </div>
              <span className="sale-order-count badge badge-primary">
                {lineCount}
              </span>
            </div>
            <div className="sale-order-target mb-3 flex items-center gap-2 rounded-lg bg-base-100/70! p-3 text-sm">
              <span className="sale-target-icon shrink-0 text-primary!">
                <Gamepad2 size={17} />
              </span>
              <div className="flex min-w-0 flex-col leading-tight">
                <small className="text-xs text-base-content/60!">
                  Игровое место
                </small>
                <strong>{pc?.name ?? "Не выбрано"}</strong>
              </div>
              <span
                className={`sale-target-status ml-auto shrink-0 ${pc ? "ready" : "text-base-content/60!"}`}
              >
                {pc ? "Готово" : "Только товары"}
              </span>
            </div>
            <div className="sale-lines flex flex-col gap-2">
              {lines.length ? (
                lines.map((line) => (
                  <div
                    className="sale-line flex items-center gap-2 rounded-lg border border-primary/20! bg-base-100/70! p-2"
                    key={line.key}
                  >
                    <div className={`sale-line-icon ${line.kind} mr-2`}>
                      {line.kind === "tariff" ? (
                        <Clock3 size={15} />
                      ) : (
                        <ShoppingCart size={15} />
                      )}
                    </div>
                    <div className="sale-line-info flex flex-col min-w-0 grow">
                      <strong className="truncate font-normal text-xs">
                        {line.name}
                      </strong>
                      <small className="truncate text-xs text-base-content/30 mb-2">
                        {line.detail}
                      </small>
                      <small className="truncate text-lg font-bold">
                        {money(line.priceCents * line.quantity)}
                      </small>
                    </div>
                    <div className="sale-quantity flex items-center gap-1">
                      <button
                        type="button"
                        className="btn btn-ghost btn-circle btn-xs"
                        aria-label={`Уменьшить ${line.name}`}
                        onClick={() => changeQuantity(line.key, -1)}
                      >
                        <Minus size={13} />
                      </button>
                      <span className="badge badge-ghost">{line.quantity}</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-circle btn-xs"
                        aria-label={`Увеличить ${line.name}`}
                        onClick={() => changeQuantity(line.key, 1)}
                      >
                        <Plus size={13} />
                      </button>
                    </div>
                    <button
                      type="button"
                      className="sale-remove-line btn btn-ghost"
                      aria-label={`Удалить ${line.name}`}
                      onClick={() => removeLine(line.key)}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))
              ) : (
                <div className="sale-empty-order flex flex-col items-center gap-2 rounded-lg border border-dashed border-primary/20! p-5 text-sm text-base-content/60!">
                  <Receipt size={24} />
                  <strong>Заказ пока пуст</strong>
                  <span className="text-center">
                    Нажимайте на карточки слева, чтобы добавить время или товары
                  </span>
                </div>
              )}
            </div>
            <div className="sale-order-summary mt-3 flex flex-col gap-2 border-t border-primary/20! pt-3">
              <div>
                <span className="text-sm text-primary/60 mr-5">
                  Игровое время
                </span>
                <strong className="badge badge-outline">
                  {totalMinutes ? formatDuration(totalMinutes) : "без тарифов"}
                </strong>
              </div>
              <div>
                <span className="text-sm text-primary/60 mr-5">Товары</span>
                <strong className="badge badge-outline">
                  {productLines.length
                    ? `${productLines.reduce((sum, line) => sum + line.quantity, 0)} шт.`
                    : "—"}
                </strong>
              </div>
              <div className="sale-total-row flex items-center justify-between text-lg font-bold border border-primary/40! px-3 py-3 rounded-lg">
                <span>Итого к оплате</span>
                <strong>{money(totalCents)}</strong>
              </div>
            </div>
            {mixedTariffs && (
              <div className="sale-inline-warning mt-3 rounded-lg bg-warning/10! p-3 text-sm text-warning-content!">
                <Tags size={16} />
                <span>
                  В корзине разные пакеты времени. Оформите их отдельными
                  покупками.
                </span>
              </div>
            )}
            <div className="sale-payment mt-4 border-t border-primary/20! pt-4">
              <div className="sale-payment-heading mb-2 flex items-center justify-between gap-3 text-xs text-base-content/70!">
                <span>
                  {activeClientSession && timeLines.length
                    ? "Способ оплаты тарифа для активного клиента"
                    : "Способ оплаты товаров и гостевого времени"}
                </span>
              </div>
              <div className="sale-payment-tabs grid rounded-lg grid-cols-2 gap-1 border border-primary/20! bg-base-100/70! p-1 my-3">
                <button
                  type="button"
                  className={`btn btn-sm ${paymentMethod === "cash" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  onClick={() => setPaymentMethod("cash")}
                >
                  <Receipt size={15} /> Наличные
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${paymentMethod === "transfer" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  onClick={() => setPaymentMethod("transfer")}
                >
                  <ArrowRightLeft size={15} /> Перевод
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${paymentMethod === "balance" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  disabled={!client}
                  onClick={() => setPaymentMethod("balance")}
                >
                  <WalletCards size={15} /> Баланс
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${paymentMethod === "mixed" ? "bg-primary! text-primary-content!" : "btn-ghost text-base-content/70!"}`}
                  disabled={!mixedSaleSupported}
                  onClick={() => {
                    const half = (
                      (timeLines.length ? timeTotalCents : productTotalCents) /
                      200
                    ).toFixed(2);
                    setPaymentMethod("mixed");
                    if (!cashPartAmount) setCashPartAmount(half);
                    if (!transferPartAmount) setTransferPartAmount(half);
                  }}
                >
                  <Tags size={15} /> Смешанная
                </button>
              </div>
              {api && client && timeLines.length > 0 && !isXbox && (
                <label className="mt-3 flex items-center gap-3 text-sm">
                  <input type="checkbox" className="toggle toggle-primary" checked={useBonus && paymentMethod === "balance"} disabled={submitting} onChange={(event) => { setUseBonus(event.target.checked); if (event.target.checked) setPaymentMethod("balance"); }} />
                  Использовать бонусы для пакетов
                </label>
              )}
              {useBonus && paymentMethod === "balance" && <p className="mt-2 text-xs text-base-content/60">Перед каждым пакетом покажем серверный расчёт. Денежная часть и товары оплачиваются с депозита.</p>}
              {activeClientSession && timeLines.length && (
                <p className="sale-payment-hint">
                  Пакет будет сразу подключён к текущей сессии выбранным
                  способом оплаты.
                </p>
              )}
              {paymentMethod === "mixed" && (
                <div className="sale-payment-parts grid grid-cols-1 gap-2 md:grid-cols-2 mb-2">
                  <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">
                    Наличными
                    <input
                      className="input input-sm"
                      aria-label="Сумма наличными"
                      inputMode="decimal"
                      value={cashPartAmount}
                      onChange={(event) =>
                        setCashPartAmount(event.target.value)
                      }
                    />
                    {""}
                  </label>
                  <label className="amount-field flex flex-col gap-1 text-xs text-base-content/60!">
                    Переводом
                    <input
                      className="input input-sm"
                      aria-label="Сумма переводом"
                      inputMode="decimal"
                      value={transferPartAmount}
                      onChange={(event) =>
                        setTransferPartAmount(event.target.value)
                      }
                    />{" "}
                  </label>
                </div>
              )}
            </div>
            {error && (
              <div
                className="sale-form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
                role="alert"
              >
                {error}
              </div>
            )}
            {success && (
              <div
                className="sale-form-success rounded-lg border border-success/40! bg-success/10! p-3 text-sm text-success-content!"
                role="status"
              >
                {success}
              </div>
            )}
            <button
              className="sale-submit-button btn btn-primary w-full bg-primary! text-primary-content! mt-3"
              disabled={submitting || !lines.length || mixedTariffs}
            >
              {submitting
                ? "Проводим заказ…"
                : useBonus && paymentMethod === "balance" ? "Рассчитать оплату пакетов" : `Оформить продажу · ${money(totalCents)}`}
              <ChevronRight size={17} />
            </button>
            <button
              type="button"
              className="sale-cancel-button btn btn-error btn-outline w-full mt-3"
              disabled={submitting}
              onClick={onClose}
            >
              Отмена
            </button>
          </form>
        </div>
      </section>
      {bonusConfirmation && <BonusPackageConfirmation {...bonusConfirmation} onConfirm={() => finishBonusConfirmation(true)} onCancel={() => finishBonusConfirmation(false)} />}
    </div>
  );
}
