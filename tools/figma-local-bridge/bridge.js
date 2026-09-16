#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const http = require("node:http");

const HOST = "localhost";
const PORT = Number.parseInt(process.env.FIGMA_BRIDGE_PORT ?? "3847", 10);
const REQUEST_TIMEOUT_MS = 30_000;
const MAX_MESSAGE_BYTES = 256 * 1024;
let token = null;

let pluginSocket = null;
let nextRequestId = 1;
const pending = new Map();

const tools = [
  {
    name: "figma_status",
    description: "Return the active Figma page and selection from the connected local development plugin.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "figma_apply_batch",
    description: "Create native Figma frames, auto-layouts, rectangles, ellipses, and text through an allowlisted batch. No arbitrary JavaScript or deletion is supported.",
    inputSchema: {
      type: "object",
      required: ["operations"],
      additionalProperties: false,
      properties: {
        selectCreated: { type: "boolean" },
        operations: {
          type: "array",
          minItems: 1,
          maxItems: 40,
          items: {
            type: "object",
            required: ["kind"],
            properties: {
              kind: { enum: ["frame", "auto_layout", "rectangle", "ellipse", "text"] },
              ref: { type: "string" }, parent: { type: "string" }, name: { type: "string" },
              x: { type: "number" }, y: { type: "number" }, width: { type: "number" }, height: { type: "number" },
              cornerRadius: { type: "number" }, direction: { enum: ["horizontal", "vertical"] }, gap: { type: "number" }, padding: { type: "number" },
              characters: { type: "string" }, fontFamily: { enum: ["Inter", "Noto Sans", "Roboto"] }, fontStyle: { type: "string" }, fontSize: { type: "number" }, textWidth: { type: "number" },
              fill: { "$ref": "#/definitions/color" }, stroke: { "$ref": "#/definitions/color" }, strokeWeight: { type: "number" }
            },
            additionalProperties: false,
          },
        },
      },
      definitions: {
        color: {
          type: "object", required: ["r", "g", "b"], additionalProperties: false,
          properties: { r: { type: "number", minimum: 0, maximum: 1 }, g: { type: "number", minimum: 0, maximum: 1 }, b: { type: "number", minimum: 0, maximum: 1 }, opacity: { type: "number", minimum: 0, maximum: 1 } },
        },
      },
    },
  },
];

const server = http.createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    response.end(JSON.stringify({ ok: true, pluginConnected: Boolean(pluginSocket) }));
    return;
  }
  response.writeHead(404).end();
});

server.on("upgrade", (request, socket) => {
  const url = new URL(request.url, `http://${HOST}:${PORT}`);
  if (url.pathname !== "/bridge" || !sameSecret(url.searchParams.get("token"), token)) {
    socket.write("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
    socket.destroy();
    return;
  }
  const key = request.headers["sec-websocket-key"];
  if (typeof key !== "string" || request.headers.upgrade?.toLowerCase() !== "websocket") {
    socket.write("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
    socket.destroy();
    return;
  }
  const accept = crypto.createHash("sha1").update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
  socket.write(["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket", "Connection: Upgrade", `Sec-WebSocket-Accept: ${accept}`, "\r\n"].join("\r\n"));
  attachPluginSocket(socket);
});

function attachPluginSocket(socket) {
  if (pluginSocket) pluginSocket.destroy();
  pluginSocket = socket;
  let buffer = Buffer.alloc(0);
  socket.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    const parsed = decodeWebSocketFrames(buffer);
    buffer = parsed.remaining;
    for (const frame of parsed.frames) {
      if (frame.opcode === 0x8) return socket.end();
      if (frame.opcode === 0x9) sendWebSocketFrame(socket, frame.payload, 0xA);
      if (frame.opcode !== 0x1) continue;
      try { handlePluginMessage(JSON.parse(frame.payload.toString("utf8"))); }
      catch { socket.end(); }
    }
  });
  socket.on("close", () => {
    if (pluginSocket === socket) pluginSocket = null;
  });
  socket.on("error", () => socket.destroy());
}

function handlePluginMessage(message) {
  if (message?.type === "plugin-hello") return;
  if (message?.type !== "plugin-result" || typeof message.requestId !== "string") return;
  const waiting = pending.get(message.requestId);
  if (!waiting) return;
  pending.delete(message.requestId);
  clearTimeout(waiting.timeout);
  message.ok ? waiting.resolve(message.result) : waiting.reject(new Error(message.error || "Figma plugin rejected the request"));
}

function requestPlugin(command, arguments_) {
  if (!pluginSocket || pluginSocket.destroyed) return Promise.reject(new Error("No Figma development plugin is connected"));
  const requestId = `req-${nextRequestId++}`;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pending.delete(requestId);
      reject(new Error("Figma plugin did not respond within 30 seconds"));
    }, REQUEST_TIMEOUT_MS);
    pending.set(requestId, { resolve, reject, timeout });
    sendWebSocketFrame(pluginSocket, Buffer.from(JSON.stringify({ type: "plugin-request", requestId, command, arguments: arguments_ })));
  });
}

function handleMcpMessage(message) {
  if (!message || typeof message !== "object" || typeof message.method !== "string") return;
  if (message.method === "notifications/initialized") return;
  if (message.method === "initialize") {
    return sendMcpResult(message.id, { protocolVersion: "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "hubshell-figma-local-bridge", version: "0.1.0" } });
  }
  if (message.method === "tools/list") return sendMcpResult(message.id, { tools });
  if (message.method === "tools/call") return callTool(message);
  return sendMcpError(message.id, -32601, "Method not found");
}

async function callTool(message) {
  const name = message.params?.name;
  const args = message.params?.arguments ?? {};
  try {
    let result;
    if (name === "figma_status") result = await requestPlugin("get_status", {});
    else if (name === "figma_apply_batch") result = await requestPlugin("apply_batch", args);
    else throw new Error("Unknown tool");
    sendMcpResult(message.id, { content: [{ type: "text", text: JSON.stringify(result) }] });
  } catch (error) {
    sendMcpResult(message.id, { content: [{ type: "text", text: error instanceof Error ? error.message : "Bridge error" }], isError: true });
  }
}

function sendMcpResult(id, result) { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n"); }
function sendMcpError(id, code, message) { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n"); }

function sameSecret(candidate, secret) {
  if (typeof candidate !== "string") return false;
  const candidateBuffer = Buffer.from(candidate);
  const secretBuffer = Buffer.from(secret);
  return candidateBuffer.length === secretBuffer.length && crypto.timingSafeEqual(candidateBuffer, secretBuffer);
}

function sendWebSocketFrame(socket, payload, opcode = 0x1) {
  if (payload.length > MAX_MESSAGE_BYTES) throw new Error("WebSocket payload exceeds the bridge limit");
  let header;
  if (payload.length < 126) header = Buffer.from([0x80 | opcode, payload.length]);
  else header = Buffer.from([0x80 | opcode, 126, payload.length >> 8, payload.length & 0xff]);
  socket.write(Buffer.concat([header, payload]));
}

function decodeWebSocketFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (offset + 2 <= buffer.length) {
    const first = buffer[offset];
    const second = buffer[offset + 1];
    const masked = (second & 0x80) !== 0;
    let length = second & 0x7f;
    let cursor = offset + 2;
    if (length === 126) {
      if (cursor + 2 > buffer.length) break;
      length = buffer.readUInt16BE(cursor); cursor += 2;
    } else if (length === 127) {
      throw new Error("Large WebSocket frames are not supported");
    }
    if (length > MAX_MESSAGE_BYTES) throw new Error("WebSocket payload exceeds the bridge limit");
    if (!masked || cursor + 4 + length > buffer.length) break;
    const mask = buffer.subarray(cursor, cursor + 4); cursor += 4;
    const payload = Buffer.alloc(length);
    for (let index = 0; index < length; index += 1) payload[index] = buffer[cursor + index] ^ mask[index % 4];
    frames.push({ opcode: first & 0x0f, payload });
    offset = cursor + length;
  }
  return { frames, remaining: buffer.subarray(offset) };
}

function start() {
  token = process.env.FIGMA_BRIDGE_TOKEN;
  if (!token || token.length < 24) {
    process.stderr.write("FIGMA_BRIDGE_TOKEN must be a random value of at least 24 characters.\n");
    process.exit(2);
  }
  if (!Number.isInteger(PORT) || PORT < 1024 || PORT > 65535) {
    process.stderr.write("FIGMA_BRIDGE_PORT must be a valid unprivileged TCP port.\n");
    process.exit(2);
  }
  process.stdin.setEncoding("utf8");
  let stdioBuffer = "";
  process.stdin.on("data", (chunk) => {
    stdioBuffer += chunk;
    let newline;
    while ((newline = stdioBuffer.indexOf("\n")) >= 0) {
      const line = stdioBuffer.slice(0, newline).trim();
      stdioBuffer = stdioBuffer.slice(newline + 1);
      if (!line) continue;
      try { handleMcpMessage(JSON.parse(line)); }
      catch { sendMcpError(null, -32700, "Parse error"); }
    }
  });
  server.listen(PORT, HOST, () => {
    process.stderr.write(`Figma local bridge listening on ws://${HOST}:${PORT}/bridge\n`);
  });
}

if (require.main === module) start();

module.exports = { decodeWebSocketFrames, sendWebSocketFrame, sameSecret, start };
