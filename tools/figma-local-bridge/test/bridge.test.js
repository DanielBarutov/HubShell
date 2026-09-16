"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { decodeWebSocketFrames, sameSecret } = require("../bridge.js");

function maskedFrame(text, mask = Buffer.from([1, 2, 3, 4])) {
  const source = Buffer.from(text);
  const encoded = Buffer.alloc(source.length);
  for (let index = 0; index < source.length; index += 1) encoded[index] = source[index] ^ mask[index % 4];
  return Buffer.concat([Buffer.from([0x81, 0x80 | source.length]), mask, encoded]);
}

test("decodes a browser-masked text WebSocket frame", () => {
  const decoded = decodeWebSocketFrames(maskedFrame('{"type":"plugin-hello"}'));
  assert.equal(decoded.frames.length, 1);
  assert.equal(decoded.frames[0].opcode, 1);
  assert.equal(decoded.frames[0].payload.toString(), '{"type":"plugin-hello"}');
  assert.equal(decoded.remaining.length, 0);
});

test("keeps an incomplete WebSocket frame buffered", () => {
  const frame = maskedFrame("ok");
  const decoded = decodeWebSocketFrames(frame.subarray(0, 5));
  assert.equal(decoded.frames.length, 0);
  assert.deepEqual(decoded.remaining, frame.subarray(0, 5));
});

test("compares bridge secrets without accepting a prefix", () => {
  assert.equal(sameSecret("123456789012345678901234", "123456789012345678901234"), true);
  assert.equal(sameSecret("12345678901234567890123", "123456789012345678901234"), false);
});
