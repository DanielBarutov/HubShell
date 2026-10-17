import { useEffect, useRef } from "react";
import type { BackendBonusGameQuote } from "../../api";

const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2 })} ₽`;

export function BonusPackageConfirmation({ quote, name, position, onConfirm, onCancel }: {
  quote: BackendBonusGameQuote;
  name: string;
  position: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);

  return (
    <dialog ref={dialog} className="modal" aria-labelledby="bonus-package-title" onCancel={(event) => { event.preventDefault(); onCancel(); }}>
      <div className="modal-box border border-primary/20">
        <h3 id="bonus-package-title" className="text-lg font-bold">Подтвердить оплату бонусами</h3>
        <p className="mt-2">{name} · пакет {position}</p>
        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <dt>Цена после скидок</dt><dd className="text-right">{money(quote.price_cents)}</dd>
          <dt>Оплата бонусами</dt><dd className="text-right">{money(quote.bonus_cents)}</dd>
          <dt>С депозита</dt><dd className="text-right font-bold">{money(quote.money_cents)}</dd>
          <dt>Начисление за покупку</dt><dd className="text-right">{money(quote.earned_bonus_cents)}</dd>
          <dt>Доступно бонусов</dt><dd className="text-right">{money(quote.available_bonus_cents)}</dd>
          <dt>Зарезервировано для игры</dt><dd className="text-right">{money(quote.reserved_bonus_cents)}</dd>
        </dl>
        {!quote.bonus_allowed && <p role="alert" className="alert alert-warning mt-4">Бонусная оплата недоступна. Можно оплатить пакет с депозита.</p>}
        {!quote.can_pay && <p role="alert" className="alert alert-error mt-4">Недостаточно средств с учётом допустимого долга.</p>}
        <p className="mt-4 text-xs text-base-content/60">Пакеты оформляются по одному. Уже подтверждённые покупки сохраняются при отмене следующих. Начисления во время игры доступны после завершения сессии.</p>
        <div className="modal-action">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Отменить оставшуюся продажу</button>
          <button type="button" className="btn btn-primary" disabled={!quote.can_pay} onClick={onConfirm}>Подтвердить покупку пакета</button>
        </div>
      </div>
    </dialog>
  );
}
