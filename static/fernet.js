/*
 * Fernet (https://github.com/fernet/spec) on top of the browser's WebCrypto API.
 *
 *   token = 0x80 || timestamp (8 bytes, big endian) || IV (16) || AES-128-CBC ciphertext || HMAC-SHA256 (32)
 *   key   = signing key (16 bytes) || encryption key (16 bytes), URL-safe base64
 *
 * The HMAC is verified (by WebCrypto, in constant time) BEFORE any decryption.
 * No third-party code is involved, so the page needs no CDN and can run under
 * a strict Content-Security-Policy. Works in browsers (secure context) and in
 * Node.js >= 19 (used by tests/js/fernet.test.mjs).
 */
(function (root, factory) {
  "use strict";
  const api = factory(root.crypto);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.PhyRandFernet = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (crypto) {
  "use strict";

  const VERSION = 0x80;
  const HEADER_LEN = 1 + 8 + 16;
  const MAC_LEN = 32;
  const BLOCK = 16;

  class InvalidToken extends Error {
    constructor(message) {
      super(message || "Invalid token: wrong key or modified data");
      this.name = "InvalidToken";
    }
  }

  function b64urlDecode(text) {
    if (typeof text !== "string" || !/^[A-Za-z0-9_-]*={0,2}$/.test(text) || text.length % 4 === 1) {
      throw new InvalidToken("Not URL-safe base64");
    }
    const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  }

  function b64urlEncode(bytes) {
    let binary = "";
    const CHUNK = 0x8000; // avoid call-stack limits on large files
    for (let i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_");
  }

  async function importKeys(keyText) {
    let raw;
    try {
      raw = b64urlDecode(keyText);
    } catch (e) {
      throw new Error("Fernet key is not valid URL-safe base64");
    }
    if (raw.length !== 32) throw new Error("Fernet key must be 32 bytes");
    const subtle = crypto.subtle;
    const signing = await subtle.importKey(
      "raw", raw.slice(0, 16), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]
    );
    const encryption = await subtle.importKey(
      "raw", raw.slice(16, 32), { name: "AES-CBC" }, false, ["encrypt", "decrypt"]
    );
    raw.fill(0);
    return { signing, encryption };
  }

  /**
   * Encrypt a Uint8Array. Returns the token as a URL-safe base64 string.
   * `options.iv` and `options.now` exist only so tests can reproduce the spec vectors.
   */
  async function encrypt(keyText, plaintext, options) {
    const opts = options || {};
    const keys = await importKeys(keyText);
    const iv = opts.iv || crypto.getRandomValues(new Uint8Array(BLOCK));
    if (iv.length !== BLOCK) throw new Error("IV must be 16 bytes");
    const seconds = BigInt(opts.now !== undefined ? opts.now : Math.floor(Date.now() / 1000));
    const ciphertext = new Uint8Array(
      await crypto.subtle.encrypt({ name: "AES-CBC", iv }, keys.encryption, plaintext)
    );
    const body = new Uint8Array(HEADER_LEN + ciphertext.length);
    body[0] = VERSION;
    new DataView(body.buffer).setBigUint64(1, seconds, false);
    body.set(iv, 9);
    body.set(ciphertext, HEADER_LEN);
    const mac = new Uint8Array(await crypto.subtle.sign("HMAC", keys.signing, body));
    const token = new Uint8Array(body.length + MAC_LEN);
    token.set(body, 0);
    token.set(mac, body.length);
    return b64urlEncode(token);
  }

  /** Verify and decrypt a token string. Throws InvalidToken on any failure. */
  async function decrypt(keyText, tokenText) {
    const keys = await importKeys(keyText);
    const token = b64urlDecode(String(tokenText).trim());
    const ctLen = token.length - HEADER_LEN - MAC_LEN;
    if (ctLen < BLOCK || ctLen % BLOCK !== 0 || token[0] !== VERSION) throw new InvalidToken();
    const body = token.subarray(0, token.length - MAC_LEN);
    const mac = token.subarray(token.length - MAC_LEN);
    const authentic = await crypto.subtle.verify("HMAC", keys.signing, mac, body);
    if (!authentic) throw new InvalidToken();
    try {
      const iv = token.subarray(9, HEADER_LEN);
      const plaintext = await crypto.subtle.decrypt(
        { name: "AES-CBC", iv }, keys.encryption, token.subarray(HEADER_LEN, token.length - MAC_LEN)
      );
      return new Uint8Array(plaintext);
    } catch (e) {
      throw new InvalidToken();
    }
  }

  return { encrypt, decrypt, InvalidToken, b64urlEncode, b64urlDecode };
});
