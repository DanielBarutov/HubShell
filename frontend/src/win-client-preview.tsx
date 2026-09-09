import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Check,
  ChevronRight,
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
  ShieldCheck,
  ShoppingBag,
  TimerReset,
  X,
} from "lucide-react";
import "./win-client-preview.css";

type PreviewMode = "login" | "widget";

const promptByMode: Record<PreviewMode, string> = {
  login:
    "Тёмный полноэкранный экран входа HUBSHELL без аватара. Графитовый фон, lime-акцент, PC9 и зона, понятный статус места, вход по нику или телефону и паролю. Без технических подсказок и лишних горячих клавиш.",
  widget:
    "Компактный borderless-виджет HUBSHELL справа на рабочем столе Windows. Без аватара и выбора темы: ник, телефон, выход, баланс, остаток минут по балансу, таймер активной поминутной сессии до минут, покупка тарифа и свёрнутый перенос места.",
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
    <main className="preview-shell">
      <header className="preview-toolbar">
        <div className="preview-brand">
          <span className="preview-brand-mark"><Gamepad2 size={15} /></span>
          <strong>HUBSHELL</strong>
          <span className="preview-badge">WIN CLIENT · DESIGN LAB</span>
        </div>
        <div className="preview-toolbar-right">
          <span className="preview-toolbar-note"><span className="preview-live-dot" /> Интерактивный макет · backend не подключён</span>
          <button className="preview-reset" onClick={() => setTimer(6512)}><RefreshCw size={13} /> Сбросить таймер</button>
        </div>
      </header>

      <div className="preview-layout">
        <section className="preview-canvas">
          <div className="canvas-heading">
            <div>
              <p className="canvas-eyebrow">Визуальная проверка</p>
              <h1>{mode === "login" ? "Экран входа" : "Виджет активной сессии"}</h1>
            </div>
            <div className="mode-switch" role="tablist" aria-label="Состояние клиента">
              <button className={mode === "login" ? "selected" : ""} onClick={() => setMode("login")} role="tab" aria-selected={mode === "login"}>Вход</button>
              <button className={mode === "widget" ? "selected" : ""} onClick={() => setMode("widget")} role="tab" aria-selected={mode === "widget"}>Виджет</button>
            </div>
          </div>

          <div className={`desktop-stage ${mode}`}>
            <div className="wallpaper-orb orb-one" />
            <div className="wallpaper-orb orb-two" />
            <div className="wallpaper-grid" />
            <div className="desktop-caption"><Monitor size={13} /> PC9 · Обычный зал</div>
            {mode === "login" ? (
              <LoginScreen passwordVisible={passwordVisible} onTogglePassword={() => setPasswordVisible((value) => !value)} onOpenWidget={() => setMode("widget")} />
            ) : (
              <WidgetScreen timer={timer} onBackToLogin={() => setMode("login")} />
            )}
          </div>
        </section>

        <aside className="preview-inspector">
          <div className="inspector-heading">
            <div>
              <p className="canvas-eyebrow">Контекст макета</p>
              <h2>{mode === "login" ? "До авторизации" : "После авторизации"}</h2>
            </div>
            <span className="inspector-index">0{mode === "login" ? 1 : 2}</span>
          </div>
          <div className="inspector-divider" />
          <div className="inspector-block">
            <span className="inspector-label">Что проверяем</span>
            <p>{mode === "login" ? "Первый кадр без белого экрана, понятный вход по паролю и состояние игрового места." : "Правый компактный виджет: пользователь, баланс, остаток времени и основное действие."}</p>
          </div>
          <div className="inspector-block">
            <span className="inspector-label">Цветовая система</span>
            <div className="swatch-row"><i className="swatch graphite" /><span>Graphite · #0A0D12</span></div>
            <div className="swatch-row"><i className="swatch lime" /><span>Lime · #B6F35A</span></div>
            <div className="swatch-row"><i className="swatch cyan" /><span>Signal · #61D8FF</span></div>
          </div>
          <div className="inspector-block prompt-block">
            <div className="prompt-label-row"><span className="inspector-label">Промпт для следующей итерации</span><button onClick={() => void copyPrompt()}>{copied ? <Check size={13} /> : <span>Копировать</span>}</button></div>
            <p className="prompt-text">{prompt}</p>
          </div>
          <div className="inspector-footer"><ShieldCheck size={14} /> Это только визуальный прототип: кнопки не вызывают реальные операции.</div>
        </aside>
      </div>
    </main>
  );
}

function LoginScreen({ passwordVisible, onTogglePassword, onOpenWidget }: { passwordVisible: boolean; onTogglePassword: () => void; onOpenWidget: () => void }) {
  return (
    <div className="login-window">
      <div className="login-topline">
        <div className="window-brand"><span className="window-brand-mark"><Gamepad2 size={15} /></span><span>HUBSHELL</span></div>
      </div>
      <div className="login-content">
        <div className="login-intro">
          <span className="intro-chip"><Check size={13} /> МЕСТО ДОСТУПНО</span>
          <h2>Войдите и начните<br /><em>играть</em></h2>
          <p>Войдите в аккаунт клуба, чтобы начать сессию на PC9.</p>
          <div className="station-card">
            <div className="station-icon"><Monitor size={28} /></div>
            <div><span>ИГРОВОЕ МЕСТО</span><strong>PC9</strong><small>Обычный зал · ряд 2</small></div>
            <span className="station-check"><Check size={14} /></span>
          </div>
          <div className="intro-note"><LockKeyhole size={14} /><span>Защищённый вход по паролю</span></div>
        </div>
        <div className="login-form-panel">
          <div className="form-heading"><span className="form-step">01 / 01</span><h3>Войти в аккаунт</h3><p>Ник или телефон и пароль</p></div>
          <label>Ник или телефон<input defaultValue="Test" placeholder="Например, player_01" /></label>
          <label>Пароль<div className="password-input"><input defaultValue="gameclub123" type={passwordVisible ? "text" : "password"} placeholder="Введите пароль" /><button type="button" onClick={onTogglePassword} aria-label="Показать пароль">{passwordVisible ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
          <button className="lime-button" onClick={onOpenWidget}>Войти <ArrowRight size={16} /></button>
          <button className="outline-button">Создать аккаунт <ChevronRight size={15} /></button>
          <div className="form-bottom"><span><ShieldCheck size={13} /> Данные передаются серверу клуба</span><button>Нужна помощь?</button></div>
        </div>
      </div>
      <div className="login-footer"><span><span className="connection-dot" /> Подключение установлено</span><span>PC9 · Обычный зал</span></div>
    </div>
  );
}

function WidgetScreen({ timer, onBackToLogin }: { timer: number; onBackToLogin: () => void }) {
  return (
    <div className="widget-window">
      <div className="widget-header">
        <div className="widget-brand"><span className="window-brand-mark"><Gamepad2 size={13} /></span><span>HUBSHELL</span></div>
        <div className="widget-window-actions"><button title="Скрыть в трей"><PanelRightClose size={15} /></button><button title="Закрыть"><X size={16} /></button></div>
      </div>
      <div className="widget-user-row"><div><span className="widget-kicker">ВЫ ВОШЛИ КАК</span><strong>Test</strong><small>+7 (999) 123-45-67</small></div><button className="logout-button" onClick={onBackToLogin}><LogOut size={15} /> Выйти</button></div>
      <div className="widget-connection"><span className="connection-dot" /> Соединение установлено <span>PC9 · Обычный зал</span></div>
      <div className="widget-balance-grid"><div className="widget-balance-card"><span>БАЛАНС</span><strong>420 ₽</strong><small>обновлено сейчас</small></div><div className="widget-balance-card lime-tint"><span>ОСТАТОК ПО БАЛАНСУ</span><strong>2 ч 48 мин</strong><small>по ставке 2,50 ₽/мин</small></div></div>
      <div className="active-session-card"><div className="active-card-top"><span className="active-pill"><i /> СЕССИЯ АКТИВНА</span><span className="active-place">PC9</span></div><div className="active-card-main"><div><span className="widget-kicker">ТЕКУЩИЙ РЕЖИМ</span><h3>Поминутная игра</h3><p>Бесплатные 5 минут завершены</p></div><div className="live-timer"><Clock3 size={15} /><strong>{formatTimer(timer)}</strong><span>осталось по балансу</span></div></div><div className="rate-row"><span><TimerReset size={13} /> Списывается автоматически</span><b>2,50 ₽ / мин</b></div></div>
      <div className="widget-section-heading"><div><span className="widget-kicker">ДОСТУПНО В АККАУНТЕ</span><strong>Тарифы времени</strong></div><button className="mini-icon-button" title="Все тарифы"><ChevronRight size={15} /></button></div>
      <div className="tariff-row"><div className="tariff-card"><div className="tariff-icon"><Clock3 size={16} /></div><div><strong>1 час</strong><span>Обычный зал</span></div><b>150 ₽</b></div><div className="tariff-card"><div className="tariff-icon purple"><Clock3 size={16} /></div><div><strong>3 часа</strong><span>Обычный зал</span></div><b>380 ₽</b></div></div>
      <button className="buy-button"><ShoppingBag size={16} /> Купить тариф <ChevronRight size={15} /></button>
      <div className="widget-bottom-row"><button className="secondary-widget-button"><ArrowRight size={14} /> Перенести сессию</button></div>
      <div className="widget-shortcuts"><span><Power size={12} /> Завершить сессию и перезапустить ПК</span></div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

export default App;
