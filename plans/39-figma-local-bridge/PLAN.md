# План 39 — локальный Figma canvas bridge

Статус: `in_progress`  
Владелец: `tools/figma-local-bridge/`  
Зависимости: Figma Desktop, edit-доступ к открытому Figma Design-файлу, локальный Codex

## Цель

Создать development-only authoring-инструмент для макетов HubShell: Codex передаёт
декларативные команды через MCP stdio, локальный bridge доставляет их в вручную
запущенный Figma dev-плагин, а плагин создаёт нативные canvas layers через Figma
Plugin API. Инструмент не является частью `win-client` и не меняет продуктовые
контракты, backend, protobuf или Windows-клиент.

## Входит

- localhost-only bridge с секретом одной сессии из environment;
- Figma dev-plugin с UI для ручного подключения bridge;
- allowlist: status, frame, auto-layout, rectangle, ellipse и text;
- валидация геометрии, цветов, размера batch и allowlisted font families;
- MCP tools `figma_status` и `figma_apply_batch`;
- README с ручным setup и protocol checks.

## Не входит

- Figma REST/PAT/OAuth, облачный Figma MCP или обход его квот;
- arbitrary JavaScript, удаление/массовое изменение существующих слоёв;
- фоновые задачи, доступ к неоткрытым файлам, network access за пределами loopback;
- изменение визуальных либо бизнес-правил HubShell через сам инструмент.

## Архитектура

```text
Codex ── stdio MCP ── bridge (localhost:3847) ── WebSocket ── plugin UI
                                                               │ postMessage
                                                               ▼
                                                        Figma Plugin API
```

Плагин должен оставаться открытым в Figma Design-файле; Figma не поддерживает
background plugins. Bridge слушает только loopback, требует случайный
`FIGMA_BRIDGE_TOKEN`, ограничивает payload/timeout и не выводит token в MCP
output. Токен не сохраняется в файлах или Git.

## Задачи

1. [x] Создать isolated directory с Figma manifest, plugin main/UI, Node MCP bridge и README.
2. [x] Ограничить plugin canvas operations декларативной allowlist и исключить arbitrary JS/delete.
3. [x] Ограничить network manifest local-only origin `http://localhost:3847`; внешние production domains отсутствуют.
4. [x] Добавить проверки WebSocket parser/secret comparison и JS syntax check.
5. [ ] Запустить Figma Desktop, импортировать local manifest, выполнить ручной pairing и `figma_status`.
6. [ ] В локальном Figma-файле создать access-gate и session widget двумя frame batches; визуально проверить native layers и Auto Layout.
7. [ ] Зафиксировать ручную Figma validation в `plans/VERIFICATION.md` и итоговый статус в `plans/SUMMARY.md`.

## Проверки

```bash
node --test tools/figma-local-bridge/test/bridge.test.js
node --check tools/figma-local-bridge/bridge.js
git diff --check
```

Ручная проверка требует Figma Desktop и edit-доступа; Linux checkout и unit checks
не доказывают работу Figma UI или право записи в конкретный облачный файл.

## Риски и открытые вопросы

- Figma может изменить Plugin API или manifest/CSP rules; setup сверяется с
  официальной документацией перед ручным запуском.
- Figma dev-plugin работает только по пользовательскому действию и в открытом
  файле; bridge не должен представляться как unattended automation.
- В первой версии новый запуск/повтор batch не идемпотентен: допустим только для
  новых artboards; update/delete существующих nodes добавляются отдельным планом
  с explicit target verification.
