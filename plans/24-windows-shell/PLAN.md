# План 24 — полноэкранная заблокированная оболочка Windows-клиента

Статус: `in_progress`  
Владелец: `win-client/`  
Связи: [`22-windows-lockdown/PLAN.md`](../22-windows-lockdown/PLAN.md), `15-win-client`

## Результат

После запуска клиент не показывает обычное окно-виджет: он занимает экран,
скрывает системный title bar и стартует в состоянии Locked. До server-backed
входа пользователя не отображаются рабочие данные, баланс или чужие операции.

## Этапы

- [x] Перевести стартовое окно на borderless fullscreen presenter.
- [x] Убрать кнопку compact/full-window из пользовательского locked flow.
- [x] Сохранять фокус и возвращать locked state при потере активации.
- [ ] Оставить compact/diagnostic режим только внутри manager maintenance.
- [x] Получать shell/lock policy после heartbeat и безопасно применять allowlist.
- [x] Проверить source-level контракт `Ctrl+Alt+P` без перехвата системных сочетаний.
- [ ] Выполнить native smoke с обычным пользователем.
- [ ] Отдельно проверить Assigned Access/Shell Launcher, Explorer, Alt+Tab,
  restart и recovery; app-level fullscreen не считать kiosk security.

## Ограничения

Прозрачный фон не должен открывать desktop или позволять обход locked shell.
Визуально используется собственная тёмная поверхность клиента; системное
ограничение выхода из Windows остаётся политикой ОС.
