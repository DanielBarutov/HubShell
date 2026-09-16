# HubShell local Figma canvas bridge

This development-only tool lets Codex call a **small allowlist** of local Figma canvas actions through a Figma dev-plugin. It does not use a Figma personal access token or REST API, and it never accepts arbitrary JavaScript from MCP.

The first version intentionally supports only:

- `figma_status` — current page and selection;
- `figma_apply_batch` — native `frame`, `auto_layout`, `rectangle`, `ellipse`, and `text` layers, with solid fills/strokes.

It cannot delete layers, read unrelated files, issue HTTP requests to Figma, or execute commands on the host.

## Prerequisites

- Node.js 20+;
- Figma Desktop, with edit rights for the target Design file;
- Codex Desktop or CLI on this same computer.

Figma development plugins must be run from the Desktop app. Keep the plugin window open while using the bridge; Figma plugins cannot run in the background.

## One-time plugin import

1. In Figma Desktop, open a **Design** file (not Dev Mode).
2. Choose **Plugins → Development → Import plugin from manifest…**.
3. Select [`manifest.json`](./manifest.json) in this directory.
4. Start **HubShell Local Canvas Bridge** from **Plugins → Development**.

The manifest permits only the local origin `http://localhost:3847`. The plugin then opens its WebSocket connection at `ws://localhost:3847/bridge`; it has no external network access.

## Start and connect

Generate a fresh one-session token locally. Do not place it in the repository, a command history, or a prompt.

```bash
export FIGMA_BRIDGE_TOKEN="$(openssl rand -hex 32)"
codex mcp add figma-local \
  --env FIGMA_BRIDGE_TOKEN="$FIGMA_BRIDGE_TOKEN" \
  -- node /home/daniel/HubShell/tools/figma-local-bridge/bridge.js
```

Restart Codex if necessary. Then, in the plugin window, leave the default URL
`ws://localhost:3847/bridge`, paste the token, and click **Подключить**.

The bridge listens only on the local `localhost` loopback interface. Its MCP stdio channel is launched by Codex; it must not be started separately in a terminal at the same time.

## Validate before a design write

Ask Codex to call `figma_status`. A successful response contains the active Figma page and selection. If it reports that no development plugin is connected, reopen the plugin and connect it with the same fresh token.

Run the automated protocol checks locally:

```bash
node --test /home/daniel/HubShell/tools/figma-local-bridge/test/bridge.test.js
node --check /home/daniel/HubShell/tools/figma-local-bridge/bridge.js
```

## Security boundary

- The bridge rejects requests without the in-memory random token.
- It binds only to loopback and handles one plugin connection at a time.
- MCP calls wait at most 30 seconds; WebSocket messages are capped at 256 KiB.
- The plugin validates geometry, colors, text length, fonts, and operation kinds.
- There is no arbitrary code tool and no delete operation in this version.

Do not expose port `3847` beyond the local machine or change the manifest to allow broad network domains.
