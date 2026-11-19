// Run with: node --test tests/js/fernet.test.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const fernet = require("../../static/fernet.js");

// Test vectors from https://github.com/fernet/spec (generate.json / verify.json).
const KEY = "cw_0x689RpI-jtRR7oE8h_eQsKImvJapLeSbXpwF4e4=";
const TOKEN =
  "gAAAAAAdwJ6wAAECAwQFBgcICQoLDA0ODy021cpGVWKZ_eEwCGM4BLLF_5CV9dOPmrhuVUPgJobwOz7JcbmrR64jVmpU4IwqDA==";
const NOW = 499162800; // 1985-10-26T01:20:00-07:00
const IV = Uint8Array.from({ length: 16 }, (_, i) => i);
const text = (s) => new TextEncoder().encode(s);

test("encrypt reproduces the Fernet spec vector", async () => {
  assert.equal(await fernet.encrypt(KEY, text("hello"), { iv: IV, now: NOW }), TOKEN);
});

test("decrypt accepts the Fernet spec vector", async () => {
  assert.equal(new TextDecoder().decode(await fernet.decrypt(KEY, TOKEN)), "hello");
});

test("round trip with random IV, binary data and a large payload", async () => {
  const data = new Uint8Array(300_000);
  for (let i = 0; i < data.length; i++) data[i] = (i * 31 + 7) & 0xff;
  const token = await fernet.encrypt(KEY, data);
  assert.notEqual(token, await fernet.encrypt(KEY, data), "IV must be random");
  assert.deepEqual(await fernet.decrypt(KEY, token), data);
});

test("empty plaintext round trips", async () => {
  const token = await fernet.encrypt(KEY, new Uint8Array(0));
  assert.equal((await fernet.decrypt(KEY, token)).length, 0);
});

test("a modified token is rejected before decryption", async () => {
  const bytes = fernet.b64urlDecode(TOKEN);
  for (const index of [0, 5, 12, 30, bytes.length - 1]) {
    const copy = Uint8Array.from(bytes);
    copy[index] ^= 0x01;
    await assert.rejects(fernet.decrypt(KEY, fernet.b64urlEncode(copy)), { name: "InvalidToken" });
  }
});

test("the wrong key is rejected", async () => {
  const other = fernet.b64urlEncode(new Uint8Array(32).fill(7));
  await assert.rejects(fernet.decrypt(other, TOKEN), { name: "InvalidToken" });
});

test("truncated or malformed tokens are rejected", async () => {
  await assert.rejects(fernet.decrypt(KEY, TOKEN.slice(0, 40)), { name: "InvalidToken" });
  await assert.rejects(fernet.decrypt(KEY, "not base64 !!"), { name: "InvalidToken" });
  await assert.rejects(fernet.decrypt(KEY, ""), { name: "InvalidToken" });
});

test("malformed keys are rejected", async () => {
  await assert.rejects(fernet.encrypt("short", text("x")));
  await assert.rejects(fernet.encrypt("!!!", text("x")));
});
