# План 24 — access-gate и post-login widget Windows-клиента

Статус: `in_progress`  
Владелец: `win-client/`  
Связи: [`22-windows-lockdown/PLAN.md`](../22-windows-lockdown/PLAN.md), `15-win-client`

## Результат

До server-backed входа клиент занимает экран, скрывает системный title bar и
стартует в состоянии Locked. После успешной авторизации он не заменяет Windows
shell: переходит к обычному Windows Desktop и показывает компактный borderless
session widget без системных кнопок окна, с собственной кнопкой скрытия в трей.
Рабочие данные, баланс и операции до входа не отображаются.

## Этапы

- [x] Перевести access-gate на borderless fullscreen presenter.
- [x] Убрать кнопку compact/full-window из пользовательского locked flow.
- [x] Сохранять фокус и возвращать locked state при потере активации.
- [ ] Реализовать переключение fullscreen gate → post-auth desktop/widget и
      tray hide/show; compact widget является штатным пользовательским режимом.
- [x] Получать shell/lock policy после heartbeat и безопасно применять только
      поддерживаемую application-часть; OS policy остаётся provisioning boundary.
- [x] Зафиксировать source-level контракт скрытого manager route через локальную
      `Ctrl+Alt+P` только на сфокусированном Locked access-gate; глобальные hooks
      и `BlockInput` не используются.
- [x] Реализовать первый application-level slice: shortcut открывает password
      form, успешный verifier переводит в Maintenance, а менеджер может скрыть
      client shell в tray для просмотра Desktop.
- [ ] Реализовать отдельный OS policy route для временного shell disable с
      правами, audit, rollback и native Windows smoke.
- [ ] Выполнить native smoke с обычным пользователем.
- [ ] Отдельно проверить Assigned Access/Shell Launcher, Explorer, Alt+Tab,
  restart и recovery; app-level fullscreen не считать kiosk security.

Связанные обязательные session/package/entry/transfer/offline задачи выполняются
по [`29-contract-alignment/PLAN.md`](../29-contract-alignment/PLAN.md), а не
локально в оконном слое.

## Ограничения

Прозрачный фон не должен открывать desktop или позволять обход locked shell.
Визуально используется собственная тёмная поверхность клиента; системное
ограничение выхода из Windows остаётся политикой ОС.
