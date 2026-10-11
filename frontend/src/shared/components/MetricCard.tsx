import type { ReactNode } from "react";
import { ArrowUpRight, TrendingUp } from "lucide-react";
import { MetricInfo, type MetricInfoData } from "./MetricInfo";

export function MetricDecoration({
  title,
  icon,
  variant,
}: {
  title: string;
  icon: ReactNode;
  variant?: "clients";
}) {
  if (variant === "clients") {
    if (title === "Всего клиентов") {
      return (
        <TrendingUp
          size={48}
          strokeWidth={1.8}
          className="text-primary/75"
          aria-hidden="true"
        />
      );
    }
    if (title === "Онлайн сейчас") {
      return (
        <div
          className="flex h-12 w-16 items-end justify-end gap-1 text-primary/75"
          aria-hidden="true"
        >
          {[3, 5, 8, 6, 10, 14].map((height, index) => (
            <i
              className="w-1.5 rounded-t-sm bg-current"
              style={{ height: `${height * 3}px` }}
              key={index}
            />
          ))}
        </div>
      );
    }
    if (title === "На депозитах" || title === "С депозитом") {
      return (
        <span
          className="size-14 rounded-full border-[9px] border-primary/20 border-r-primary border-t-primary"
          aria-hidden="true"
        />
      );
    }
  }
  const dashboardIllustrations: Record<string, string> = {
    "Выручка сегодня": "/metric-revenue.png",
    "Выручка за смену": "/metric-revenue.png",
    "Активные сессии": "/metric-sessions.png",
    "Брони сегодня": "/metric-bookings.png",
    "На депозитах": "/metric-deposit.png",
  };
  const illustration = dashboardIllustrations[title];
  if (illustration) {
    return (
      <img
        src={illustration}
        alt=""
        className="h-16 w-24 rounded-full object-cover"
      />
    );
  }
  if (
    [
      "Выручка клуба",
      "Игровое время",
      "Средняя сессия",
      "Занятость мест",
      "Клиенты с визитом",
      "Клиенты с визитами",
    ].includes(title)
  ) {
    const paths: Record<string, string> = {
      "Выручка клуба":
        "M2 28 L14 25 L25 27 L37 18 L49 23 L61 13 L73 20 L86 8 L98 14",
      "Игровое время":
        "M2 26 L15 19 L27 22 L39 10 L50 16 L62 25 L74 21 L86 7 L98 17",
      "Средняя сессия":
        "M2 28 L15 23 L28 5 L40 24 L52 17 L64 26 L76 13 L88 20 L98 18",
      "Занятость мест":
        "M2 22 L14 8 L26 20 L38 5 L50 25 L62 20 L74 23 L86 13 L98 15",
      "Клиенты с визитом":
        "M2 27 L15 24 L28 18 L40 21 L52 9 L64 17 L76 6 L88 13 L98 5",
      "Клиенты с визитами":
        "M2 27 L15 24 L28 18 L40 21 L52 9 L64 17 L76 6 L88 13 L98 5",
    };
    return (
      <svg
        className="h-14 w-28 text-primary/80 opacity-90"
        viewBox="0 0 100 34"
        fill="none"
        aria-hidden="true"
      >
        <path
          d={paths[title]}
          className="stroke-current"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={`${paths[title]} L98 34 L2 34 Z`}
          className="fill-primary/10"
        />
      </svg>
    );
  }
  if (title === "Всего клиентов")
    return (
      <svg
        className="h-14 w-28 text-primary/80 opacity-90"
        viewBox="0 0 100 34"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 28 L14 24 L26 26 L38 16 L50 21 L62 12 L74 18 L86 8 L98 13"
          className="stroke-current"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M2 28 L14 24 L26 26 L38 16 L50 21 L62 12 L74 18 L86 8 L98 13 L98 34 L2 34 Z"
          className="fill-primary/10"
        />
      </svg>
    );
  if (title === "Онлайн сейчас")
    return (
      <svg
        className="h-14 w-28 text-accent/80 opacity-90"
        viewBox="0 0 100 34"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 27 L16 19 L28 23 L41 11 L54 17 L66 24 L79 16 L90 8 L98 15"
          className="stroke-current"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M2 27 L16 19 L28 23 L41 11 L54 17 L66 24 L79 16 L90 8 L98 15 L98 34 L2 34 Z"
          className="fill-accent/10"
        />
      </svg>
    );
  if (title === "На депозитах")
    return (
      <svg
        className="h-14 w-28 text-primary/80 opacity-90"
        viewBox="0 0 100 34"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 28 L14 25 L26 18 L38 21 L50 11 L62 16 L74 9 L86 14 L98 6"
          className="stroke-current"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M2 28 L14 25 L26 18 L38 21 L50 11 L62 16 L74 9 L86 14 L98 6 L98 34 L2 34 Z"
          className="fill-primary/10"
        />
      </svg>
    );
  if (title === "Бонусы")
    return (
      <svg
        className="h-14 w-28 text-secondary/80 opacity-90"
        viewBox="0 0 100 34"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 27 L15 22 L28 25 L40 17 L53 10 L66 18 L78 12 L90 15 L98 7"
          className="stroke-current"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M2 27 L15 22 L28 25 L40 17 L53 10 L66 18 L78 12 L90 15 L98 7 L98 34 L2 34 Z"
          className="fill-secondary/10"
        />
      </svg>
    );
  if (title.includes("Выручка"))
    return (
      <div className="relative h-16 w-20 opacity-75" aria-hidden="true">
        <i className="absolute bottom-1 left-1 h-7 w-12 rounded-[50%] border-2 border-primary/45 bg-primary/10" />
        <i className="absolute bottom-4 left-3 h-7 w-12 rounded-[50%] border-2 border-primary/60 bg-primary/15" />
        <i className="absolute bottom-7 left-5 h-7 w-12 rounded-[50%] border-2 border-primary/75 bg-primary/20 shadow-[0_0_18px_rgba(168,255,77,0.25)]" />
      </div>
    );
  if (title.includes("сессии"))
    return (
      <div className="relative h-16 w-20 opacity-65" aria-hidden="true">
        <i className="absolute bottom-1 left-1 h-9 w-9 rounded-full border-2 border-accent/40 bg-accent/10" />
        <i className="absolute bottom-1 right-0 h-7 w-7 rounded-full border-2 border-accent/30 bg-accent/10" />
        <i className="absolute left-3 top-0 h-5 w-5 rounded-full bg-accent/35" />
        <i className="absolute right-1 top-4 h-4 w-4 rounded-full bg-accent/25" />
      </div>
    );
  if (title.includes("Брони"))
    return (
      <div
        className="relative h-16 w-20 rounded-xl border-2 border-primary/35 bg-primary/10 opacity-70 shadow-[0_0_18px_rgba(168,255,77,0.16)]"
        aria-hidden="true"
      >
        <div className="absolute inset-x-3 top-4 grid grid-cols-3 gap-1">
          {Array.from({ length: 9 }, (_, index) => (
            <i className="h-1.5 rounded-full bg-primary/35" key={index} />
          ))}
        </div>
        <i className="absolute -top-2 left-4 h-4 w-1 rounded-full bg-primary/50" />
        <i className="absolute -top-2 right-4 h-4 w-1 rounded-full bg-primary/50" />
      </div>
    );
  if (title.includes("депозит"))
    return (
      <div
        className="relative h-14 w-20 -skew-y-6 opacity-70"
        aria-hidden="true"
      >
        <div className="absolute inset-0 rounded-xl border-2 border-primary/45 bg-primary/10 shadow-[0_0_18px_rgba(168,255,77,0.18)]" />
        <div className="absolute inset-2 rounded-lg border border-primary/30" />
        <i className="absolute bottom-4 left-3 h-1.5 w-8 rounded-full bg-primary/50" />
      </div>
    );
  return <span className="scale-[3.8] text-primary/10">{icon}</span>;
}

export function MetricCard({
  title,
  value,
  delta,
  positive,
  icon,
  accent,
  info,
  state,
  stateLabel,
  dense,
}: {
  title: string;
  value: string;
  delta: string;
  positive?: boolean;
  icon: ReactNode;
  accent: string;
  info?: MetricInfoData;
  state?: string;
  stateLabel?: string;
  dense?: boolean;
}) {
  const displayDelta =
    stateLabel && state && state !== "ready" && state !== "available"
      ? `${stateLabel} · ${delta}`
      : delta;
  return (
    <div
      className={`card group relative ${dense ? "h-36 min-h-0! gap-1 p-2.5" : "min-h-36 gap-1.5 p-3"} z-0 overflow-visible border border-primary/25! bg-base-200/70! text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.16)] backdrop-blur-md hover:z-50 focus-within:z-50`}
      data-state={state}
    >
      <div
        className="pointer-events-none absolute right-5 top-1/2 -translate-y-1/2"
        aria-hidden="true"
      >
        <MetricDecoration title={title} icon={icon} />
      </div>
      <div
        className={`metric-icon ${accent} flex h-12 w-12 items-center justify-center rounded-lg border border-primary/30! bg-primary/20! text-primary!`}
      >
        {icon}
      </div>
      <div className="metric-title-row flex items-center justify-between gap-2 text-xs text-base-content/70!">
        <div className="metric-title">{title}</div>
        {info && <MetricInfo title={title} info={info} />}
      </div>
      <div className="metric-value text-2xl font-bold tracking-tight text-base-content!">
        {value}
      </div>
      <div
        className={`metric-delta flex items-center gap-1 text-xs ${positive ? "positive text-primary!" : "text-base-content/60!"}`}
      >
        {positive && <ArrowUpRight size={14} />}
        {displayDelta}
      </div>
    </div>
  );
}
