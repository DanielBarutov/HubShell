import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  Eye,
  EyeOff,
  Gamepad2,
  LockKeyhole,
  LogOut,
  Monitor,
  PanelRightClose,
  Power,
  RefreshCw,
  Shield,
  ShoppingBag,
  TimerReset,
  X,
} from "lucide-react";
import "./index.css";

type PreviewMode = "login" | "widget";

const promptByMode: Record<PreviewMode, string> = {
  login:
    "Тёмный полноэкранный экран входа HUBSHELL без аватара. Графитовый фон, lime-акцент, PC9 и зона, понятный статус места, вход по нику или телефону и паролю.",
  widget:
    "Компактный виджет HUBSHELL справа на рабочем столе Windows: пользователь, баланс, остаток минут, таймер активной сессии и покупка тарифа.",
};

function formatTimer(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return [hours, minutes].map((value) => String(value).padStart(2, "0")).join(":");
}

function App() {
  const [mode, setMode] = useState<PreviewMode>("login");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [timer, setTimer] = useState(6512);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (mode !== "widget") return undefined;
    const interval = window.setInterval(() => setTimer((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(interval);
  }, [mode]);

  const prompt = useMemo(() => promptByMode[mode], [mode]);

  const copyPrompt = async () => {
    await navigator.clipboard?.writeText(prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <header className="navbar min-h-16 border-b border-primary/15! bg-base-200/75! px-4 lg:px-8">
        <div className="flex flex-1 items-center gap-3">
          <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-content"><Gamepad2 size={15} /></span>
          <strong className="tracking-tight">HUBSHELL</strong>
          <span className="badge badge-outline border-primary/20! text-[9px] tracking-wider text-base-content/60">WIN CLIENT · DESIGN LAB</span>
        </div>
        <div className="hidden items-center gap-4 text-xs text-base-content/60 sm:flex">
          <span className="flex items-center gap-2 font-mono text-[10px]"><span className="size-2 rounded-full bg-primary" /> Макет · сервер не подключён</span>
          <button className="btn btn-ghost btn-xs border border-primary/20! text-base-content/70" onClick={() => setTimer(6512)}><RefreshCw size={13} /> Сбросить таймер</button>
        </div>
      </header>

      <div className="grid gap-6 p-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:p-8">
        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
            <div><p className="mb-1 font-mono text-[10px] uppercase tracking-[0.12em] text-base-content/55">Визуальная проверка</p><h1 className="text-2xl font-bold tracking-tight">{mode === "login" ? "Экран входа" : "Виджет активной сессии"}</h1></div>
            <div className="tabs tabs-box border border-primary/20! bg-base-100/55! p-1" role="tablist" aria-label="Состояние клиента">
              <button className={`tab h-8 px-3 text-xs ${mode === "login" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "text-base-content/60! hover:text-primary!"}`} onClick={() => setMode("login")} role="tab" aria-selected={mode === "login"}>Вход</button>
              <button className={`tab h-8 px-3 text-xs ${mode === "widget" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "text-base-content/60! hover:text-primary!"}`} onClick={() => setMode("widget")} role="tab" aria-selected={mode === "widget"}>Виджет</button>
            </div>
          </div>

          <div className={`relative grid min-h-[42rem] place-items-center overflow-hidden rounded-box border border-primary/20! bg-base-200/55! p-4 shadow-2xl lg:p-8 ${mode === "widget" ? "lg:place-items-start lg:justify-items-end" : ""}`}>
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_25%,rgba(182,240,106,0.2),transparent_32%),radial-gradient(circle_at_82%_78%,rgba(108,170,102,0.2),transparent_33%)]" />
            <div className="pointer-events-none absolute inset-0 opacity-10 [background-image:linear-gradient(rgba(182,240,106,0.35)_1px,transparent_1px),linear-gradient(90deg,rgba(182,240,106,0.35)_1px,transparent_1px)] [background-size:50px_50px]" />
            <div className="absolute left-5 top-4 flex items-center gap-2 font-mono text-[10px] text-base-content/50"><Monitor size={13} /> PC9 · Обычный зал</div>
            {mode === "login" ? <LoginScreen passwordVisible={passwordVisible} onTogglePassword={() => setPasswordVisible((value) => !value)} onOpenWidget={() => setMode("widget")} /> : <WidgetScreen timer={timer} onBackToLogin={() => setMode("login")} />}
          </div>
        </section>

        <aside className="card h-fit border border-primary/20! bg-base-200/55! p-5 shadow-xl">
          <div className="flex items-start justify-between gap-3"><div><p className="mb-1 font-mono text-[10px] uppercase tracking-[0.12em] text-base-content/55">Контекст макета</p><h2 className="text-lg font-bold">{mode === "login" ? "До авторизации" : "После авторизации"}</h2></div><span className="font-mono text-xs text-primary">0{mode === "login" ? 1 : 2}</span></div>
          <div className="my-5 h-px bg-primary/15!" />
          <InspectorBlock label="Что проверяем">{mode === "login" ? "Первый кадр без белого экрана, понятный вход по паролю и состояние игрового места." : "Правый компактный виджет: пользователь, баланс, остаток времени и основное действие."}</InspectorBlock>
          <InspectorBlock label="Цветовая система"><Swatch color="bg-base-300" text="Graphite · theme base" /><Swatch color="bg-primary" text="Lime · theme primary" /><Swatch color="bg-accent" text="Green · theme accent" /></InspectorBlock>
          <div className="rounded-lg border border-primary/20! bg-base-100 p-3"><div className="flex items-center justify-between gap-2"><span className="font-mono text-[10px] uppercase tracking-[0.08em] text-base-content/60">Промпт для следующей итерации</span><button className="btn btn-ghost btn-xs text-primary" onClick={() => void copyPrompt()}>{copied ? <Check size={13} /> : "Копировать"}</button></div><p className="mt-3 text-xs leading-relaxed text-base-content/70">{prompt}</p></div>
          <p className="mt-4 flex gap-2 text-[10px] leading-relaxed text-base-content/50"><Shield size={14} className="shrink-0 text-primary" /> Это только визуальный прототип: кнопки не вызывают реальные операции.</p>
        </aside>
      </div>
    </main>
  );
}

function InspectorBlock({ label, children }: { label: string; children: ReactNode }) {
  return <div className="pb-5"><span className="font-mono text-[10px] uppercase tracking-[0.08em] text-base-content/60">{label}</span><div className="mt-2 space-y-2 text-xs leading-relaxed text-base-content/70">{children}</div></div>;
}

function Swatch({ color, text }: { color: string; text: string }) {
  return <div className="flex items-center gap-2 font-mono text-[10px] text-base-content/70"><span className={`size-4 rounded ${color}`} /><span>{text}</span></div>;
}

function LoginScreen({ passwordVisible, onTogglePassword, onOpenWidget }: { passwordVisible: boolean; onTogglePassword: () => void; onOpenWidget: () => void }) {
  return (
    <div className="card relative z-10 w-full max-w-3xl border border-primary/20! bg-base-100/95 shadow-2xl">
      <div className="flex items-center gap-2 border-b border-primary/20! px-5 py-4 text-xs font-bold tracking-[0.12em] text-primary"><span className="grid size-6 place-items-center rounded-md bg-primary text-primary-content"><Gamepad2 size={14} /></span> HUBSHELL</div>
      <div className="grid gap-8 p-6 lg:grid-cols-[1fr_0.92fr] lg:p-9">
        <div className="flex flex-col justify-center"><span className="badge badge-outline w-fit gap-2 border-primary/30 bg-primary/10 px-2 text-[9px] tracking-wider text-primary"><Circle size={12} /> МЕСТО ДОСТУПНО</span><h2 className="mt-5 text-3xl font-bold leading-tight tracking-tight">Вход в игровой<br /><em className="not-italic text-primary">аккаунт</em></h2><p className="mt-3 max-w-xs text-xs leading-relaxed text-base-content/60">Введите данные аккаунта, чтобы начать игру на PC9.</p><div className="card mt-7 border border-primary/20! bg-base-200/55! p-3"><div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-lg bg-accent/20 text-accent"><Monitor size={26} /></span><span className="flex flex-1 flex-col gap-1"><small className="font-mono text-[9px] text-base-content/50">ИГРОВОЕ МЕСТО</small><strong>PC9</strong><small className="text-[10px] text-base-content/55">Обычный зал · ряд 2</small></span><span className="grid size-6 place-items-center rounded-full bg-primary text-primary-content"><Circle size={13} /></span></div></div><p className="mt-5 flex items-center gap-2 text-[10px] text-base-content/55"><LockKeyhole size={14} className="text-primary" /> Защищённый вход по паролю</p></div>
        <div className="card border border-primary/20! bg-base-200/55! p-5"><span className="font-mono text-[10px] text-base-content/55">01 / 01</span><h3 className="mt-2 text-lg font-bold">Войти в аккаунт</h3><p className="mt-1 text-xs text-base-content/60">Ник или телефон и пароль</p><label className="form-control mt-5"><span className="label-text text-xs text-base-content/70">Ник или телефон</span><input className="input input-sm input-bordered mt-1 w-full bg-base-100" defaultValue="Test" placeholder="Например, player_01" /></label><label className="form-control mt-3"><span className="label-text text-xs text-base-content/70">Пароль</span><span className="relative mt-1"><input className="input input-sm input-bordered w-full bg-base-100 pr-10" defaultValue="gameclub123" type={passwordVisible ? "text" : "password"} placeholder="Введите пароль" /><button type="button" className="btn btn-ghost btn-xs absolute right-1 top-1 text-base-content/60" onClick={onTogglePassword} aria-label="Показать пароль">{passwordVisible ? <EyeOff size={16} /> : <Eye size={16} />}</button></span></label><button className="btn btn-primary btn-sm mt-5 w-full bg-primary text-primary-content" onClick={onOpenWidget}>Войти <ArrowRight size={16} /></button><button className="btn btn-outline btn-sm mt-2 w-full border-base-content/30">Создать аккаунт <ChevronRight size={15} /></button><div className="mt-5 flex items-center justify-between gap-2 text-[9px] text-base-content/50"><span className="flex items-center gap-1"><Shield size={13} /> Данные передаются серверу клуба</span><button className="link link-hover">Нужна помощь?</button></div></div>
      </div>
      <div className="flex items-center justify-between border-t border-primary/20! px-5 py-3 font-mono text-[9px] text-base-content/50"><span className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-primary" /> Подключение установлено</span><span>PC9 · Обычный зал</span></div>
    </div>
  );
}

function WidgetScreen({ timer, onBackToLogin }: { timer: number; onBackToLogin: () => void }) {
  return (
    <div className="card relative z-10 w-full max-w-sm border border-primary/20! bg-base-100 shadow-2xl lg:mr-2">
      <div className="flex items-center justify-between border-b border-primary/20! px-4 py-3"><span className="flex items-center gap-2 text-[10px] font-bold tracking-[0.12em] text-primary"><span className="grid size-5 place-items-center rounded bg-primary text-primary-content"><Gamepad2 size={12} /></span> HUBSHELL</span><span className="flex gap-1"><button className="btn btn-ghost btn-xs text-base-content/60" title="Скрыть в трей"><PanelRightClose size={15} /></button><button className="btn btn-ghost btn-xs text-base-content/60" title="Закрыть"><X size={16} /></button></span></div>
      <div className="flex items-center justify-between gap-3 p-4"><span className="flex flex-col gap-1"><small className="font-mono text-[9px] text-base-content/50">ВЫ ВОШЛИ КАК</small><strong>Test</strong><small className="text-[10px] text-base-content/55">+7 (999) 123-45-67</small></span><button className="btn btn-outline btn-xs border-base-content/30" onClick={onBackToLogin}><LogOut size={14} /> Выйти</button></div>
      <div className="flex items-center gap-2 border-y border-primary/20! bg-base-200/55! px-4 py-2 text-[10px] text-base-content/70"><span className="size-1.5 rounded-full bg-primary" /> Соединение установлено <span className="ml-auto font-mono text-[9px] text-base-content/50">PC9 · Обычный зал</span></div>
      <div className="grid grid-cols-[1fr_1.25fr] gap-2 p-4 pb-2"><Balance title="БАЛАНС" value="420 ₽" note="обновлено сейчас" /><Balance title="ОСТАТОК ПО БАЛАНСУ" value="2 ч 48 мин" note="по ставке 2,50 ₽/мин" accent /></div>
      <div className="mx-4 mt-2 rounded-lg border border-accent/30 bg-accent/10 p-3"><div className="flex justify-between"><span className="badge badge-outline border-accent/40 text-[9px] text-accent">● СЕССИЯ АКТИВНА</span><span className="font-mono text-[9px] text-base-content/55">PC9</span></div><div className="mt-4 flex items-center justify-between gap-3"><div><small className="font-mono text-[9px] text-base-content/50">ТЕКУЩИЙ РЕЖИМ</small><h3 className="mt-1 font-bold">Поминутная игра</h3><p className="mt-1 text-[9px] text-base-content/55">Бесплатные 5 минут завершены</p></div><span className="flex flex-col items-end gap-1"><Clock3 size={15} className="text-accent" /><strong className="font-mono text-xl text-accent">{formatTimer(timer)}</strong><small className="font-mono text-[8px] text-base-content/55">осталось по балансу</small></span></div><div className="mt-4 flex items-center justify-between border-t border-accent/20 pt-2 text-[9px] text-base-content/60"><span className="flex items-center gap-1"><TimerReset size={13} /> Списывается автоматически</span><b className="font-mono text-primary">2,50 ₽ / мин</b></div></div>
      <div className="flex items-center justify-between px-4 pb-2 pt-5"><span><small className="block font-mono text-[9px] text-base-content/50">ДОСТУПНО В АККАУНТЕ</small><strong className="text-xs">Тарифы времени</strong></span><button className="btn btn-ghost btn-xs text-base-content/60" title="Все тарифы"><ChevronRight size={15} /></button></div>
      <div className="grid grid-cols-2 gap-2 px-4"><Tariff title="1 час" price="150 ₽" /><Tariff title="3 часа" price="380 ₽" /></div>
      <button className="btn btn-primary btn-sm mx-4 mt-3 w-[calc(100%-2rem)] bg-primary text-primary-content"><ShoppingBag size={15} /> Купить тариф <ChevronRight size={15} className="ml-auto" /></button><button className="btn btn-ghost btn-xs m-4 mb-3 w-fit text-base-content/70"><ArrowRight size={14} /> Перенести сессию</button><div className="border-t border-primary/20! bg-base-200/55! px-4 py-3 font-mono text-[8px] text-base-content/50"><Power size={12} className="mr-1 inline text-primary" /> Завершить сессию и перезапустить ПК</div>
    </div>
  );
}

function Balance({ title, value, note, accent = false }: { title: string; value: string; note: string; accent?: boolean }) {
  return <div className={`card border p-3 ${accent ? "border-primary/30 bg-primary/10" : "border-primary/20! bg-base-200/55!"}`}><small className="font-mono text-[8px] text-base-content/55">{title}</small><strong className={`mt-1 text-base ${accent ? "text-primary" : ""}`}>{value}</strong><small className="mt-1 text-[9px] text-base-content/50">{note}</small></div>;
}

function Tariff({ title, price }: { title: string; price: string }) {
  return <div className="card flex-row items-center gap-2 border border-primary/20! bg-base-200/55! p-2"><span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary/15 text-primary"><Clock3 size={15} /></span><span className="flex min-w-0 flex-1 flex-col"><strong className="text-[10px]">{title}</strong><small className="truncate text-[8px] text-base-content/50">Обычный зал</small></span><b className="font-mono text-[9px] text-primary">{price}</b></div>;
}

createRoot(document.getElementById("root")!).render(<App />);

export default App;
