/*
 * PhyRand web client.
 *
 * Security notes
 *  - Every server-supplied value is inserted with textContent / DOM APIs,
 *    never as HTML strings, and there are no inline event handlers, so the page
 *    runs under the server's `default-src 'self'` Content-Security-Policy.
 *  - Tokens and keys live only in memory (never written to browser storage).
 *  - Plaintext files are processed locally and are never uploaded.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const FILE_ID_RE = /^[A-Z0-9]{6,32}$/;
  const EXTENSION_RE = /^[A-Za-z0-9]{1,16}$/;

  function setMessage(id, text, kind) {
    const el = $(id);
    el.textContent = text;
    el.className = "message" + (kind ? " " + kind : "");
  }

  function safeExtension(value) {
    return typeof value === "string" && EXTENSION_RE.test(value) ? value.toLowerCase() : "bin";
  }

  async function api(method, path, token, body) {
    const headers = { Accept: "application/json" };
    if (token) headers["x-api-token"] = token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        credentials: "omit",
      });
    } catch (e) {
      throw new Error("Cannot reach the server.");
    }
    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      /* non-JSON error body */
    }
    if (!response.ok) {
      const detail = data && typeof data.detail === "string" ? data.detail : "Request failed";
      throw new Error(detail + " (HTTP " + response.status + ")");
    }
    return data;
  }

  function download(bytesOrText, name, type) {
    const url = URL.createObjectURL(new Blob([bytesOrText], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  async function withBusy(button, task) {
    button.disabled = true;
    try {
      await task();
    } finally {
      button.disabled = false;
    }
  }

  // -- tabs ---------------------------------------------------------------

  function showView(name) {
    document.querySelectorAll(".tabs button").forEach((tab) => {
      const selected = tab.dataset.view === name;
      tab.setAttribute("aria-selected", String(selected));
      $("view-" + tab.dataset.view).hidden = !selected;
    });
  }

  // -- status -------------------------------------------------------------

  async function refreshStatus() {
    const dot = $("status-dot");
    try {
      const s = await api("GET", "/heartbeat");
      const online = s.status === "ONLINE";
      dot.className = "dot " + (online ? "ok" : s.can_issue_keys ? "warn" : "bad");
      $("status-text").textContent = online ? "online" : s.can_issue_keys ? "degraded" : "not issuing keys";
      $("hardware-text").textContent = String(s.hardware).replace(/_/g, " ");
    } catch (e) {
      dot.className = "dot bad";
      $("status-text").textContent = "unreachable";
      $("hardware-text").textContent = "-";
    }
  }

  // -- decrypt ------------------------------------------------------------

  async function decryptFlow() {
    const fileId = $("dec-id").value.trim().toUpperCase();
    const token = $("dec-token").value.trim();
    const file = $("dec-file").files[0];
    if (!FILE_ID_RE.test(fileId)) return setMessage("dec-message", "Enter a valid file ID (letters and digits).", "error");
    if (!token) return setMessage("dec-message", "Enter the release token.", "error");
    if (!file) return setMessage("dec-message", "Choose the encrypted file.", "error");
    setMessage("dec-message", "Fetching key...");
    try {
      const released = await api("GET", "/release/" + encodeURIComponent(fileId), token);
      setMessage("dec-message", "Verifying and decrypting...");
      const plaintext = await PhyRandFernet.decrypt(released.key, await file.text());
      const base = file.name.replace(/\.quantum$/i, "");
      const hasExtension = base !== file.name && /\.[A-Za-z0-9]{1,16}$/.test(base);
      download(plaintext, hasExtension ? base : "restored." + safeExtension(released.extension), "application/octet-stream");
      setMessage("dec-message", "Decrypted. The file has been saved by your browser.", "success");
    } catch (e) {
      const text = e && e.name === "InvalidToken"
        ? "Decryption failed: the file was modified or does not belong to this file ID."
        : e.message;
      setMessage("dec-message", text, "error");
    }
  }

  // -- encrypt ------------------------------------------------------------

  async function encryptFlow() {
    const token = $("master-token").value.trim();
    const file = $("enc-file").files[0];
    $("enc-result").hidden = true;
    if (!token) return setMessage("enc-message", "Enter the master token.", "error");
    if (!file) return setMessage("enc-message", "Choose a file to encrypt.", "error");
    setMessage("enc-message", "Requesting key...");
    try {
      const issued = await api("POST", "/request-keys", token);
      const dot = file.name.lastIndexOf(".");
      const extension = safeExtension(dot > 0 ? file.name.slice(dot + 1) : "");
      // Escrow first: if this fails nothing has been encrypted yet.
      const committed = await api("POST", "/vault/commit", token, {
        file_id: issued.file_id,
        key: issued.key,
        extension,
      });
      setMessage("enc-message", "Encrypting locally...");
      const ciphertext = await PhyRandFernet.encrypt(issued.key, new Uint8Array(await file.arrayBuffer()));
      download(ciphertext, file.name + ".quantum", "text/plain");
      $("res-id").textContent = committed.file_id;
      $("res-token").textContent = committed.release_token;
      const source = issued.entropy && issued.entropy.source;
      $("res-source").textContent = source === "hardware+os"
        ? "noise source + OS generator (" + issued.entropy.hardware_bytes_mixed + " hardware bytes mixed in)"
        : "OS generator only (noise source unavailable)";
      $("enc-result").hidden = false;
      setMessage("enc-message", "Encrypted. The .quantum file has been saved by your browser.", "success");
    } catch (e) {
      setMessage("enc-message", e.message, "error");
    }
  }

  // -- vault --------------------------------------------------------------

  function emptyRow(text) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty";
    cell.textContent = text;
    row.appendChild(cell);
    return row;
  }

  async function refreshVault() {
    const token = $("master-token").value.trim();
    const rows = $("vault-rows");
    rows.replaceChildren();
    if (!token) return setMessage("vault-message", "Enter the master token on the Encrypt tab first.", "error");
    setMessage("vault-message", "Loading...");
    try {
      const entries = await api("GET", "/vault/list", token);
      const ids = Object.keys(entries).reverse();
      if (ids.length === 0) rows.appendChild(emptyRow("No keys are escrowed."));
      for (const id of ids) {
        const entry = entries[id] || {};
        const row = document.createElement("tr");
        const created = entry.created_at ? new Date(entry.created_at) : null;
        const cells = [
          id,
          "." + safeExtension(entry.extension),
          created && !isNaN(created) ? created.toLocaleDateString() : "-",
        ];
        for (const text of cells) {
          const cell = document.createElement("td");
          cell.textContent = text;
          row.appendChild(cell);
        }
        const action = document.createElement("td");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "revoke";
        button.textContent = "Revoke";
        button.addEventListener("click", () => revoke(id));
        action.appendChild(button);
        row.appendChild(action);
        rows.appendChild(row);
      }
      setMessage("vault-message", ids.length + (ids.length === 1 ? " key" : " keys") + " escrowed.");
    } catch (e) {
      setMessage("vault-message", e.message, "error");
    }
  }

  async function revoke(id) {
    if (!FILE_ID_RE.test(id)) return;
    if (!window.confirm("Delete the escrowed key for " + id + "? This cannot be undone.")) return;
    try {
      await api("DELETE", "/vault/revoke/" + encodeURIComponent(id), $("master-token").value.trim());
      await refreshVault();
    } catch (e) {
      setMessage("vault-message", e.message, "error");
    }
  }

  // -- wiring -------------------------------------------------------------

  document.querySelectorAll(".tabs button").forEach((tab) => {
    tab.addEventListener("click", () => {
      showView(tab.dataset.view);
      if (tab.dataset.view === "vault" && $("master-token").value.trim()) refreshVault();
    });
  });
  $("dec-button").addEventListener("click", (e) => withBusy(e.currentTarget, decryptFlow));
  $("enc-button").addEventListener("click", (e) => withBusy(e.currentTarget, encryptFlow));
  $("vault-refresh").addEventListener("click", (e) => withBusy(e.currentTarget, refreshVault));
  document.querySelectorAll("button.copy").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($(button.dataset.copy).textContent);
        button.textContent = "Copied";
        setTimeout(() => (button.textContent = "Copy"), 1500);
      } catch (e) {
        button.textContent = "Select and copy manually";
      }
    });
  });

  if (!window.isSecureContext || !window.crypto || !window.crypto.subtle) {
    const banner = $("banner");
    banner.textContent =
      "This page needs a secure context (https:// or http://localhost) for the browser's WebCrypto API. Encryption and decryption are disabled.";
    banner.hidden = false;
    $("dec-button").disabled = true;
    $("enc-button").disabled = true;
  }

  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
