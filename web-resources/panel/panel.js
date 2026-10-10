"use strict";

class ShizuPanel {
  constructor() {
    this.strings = {};
    this.csrf = "";
    this.state = null;
    this.invite = new URLSearchParams(location.hash.slice(1)).get("invite");
    history.replaceState(null, "", location.pathname);
    this.view = "settings";
    this.previewId = null;
    this.authTimer = null;
    this.logTimer = null;
    this.toastTimer = null;
    this.bind();
  }

  element(id) { return document.getElementById(id); }
  text(key) { return this.strings[key] || key; }
  format(key, ...values) {
    return this.text(key).replace(/\{(\d+)\}/g, (_, index) => values[Number(index)] ?? "");
  }

  async api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.method && options.method !== "GET") headers.set("X-CSRF-Token", this.csrf);
    if (options.json !== undefined) {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(options.json);
    }
    const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) {
      let data;
      try { data = await response.json(); } catch { data = {}; }
      if (response.status === 401) this.lock();
      const error = new Error([data.message || this.text("request_failed"), data.detail].filter(Boolean).join(" · "));
      error.status = response.status;
      throw error;
    }
    return options.blob ? response.blob() : response.json();
  }

  async translate() {
    const meta = await this.api("/api/meta");
    this.strings = meta.strings;
    this.element("demo-notice").hidden = !meta.demo;
    document.documentElement.lang = meta.language;
    document.title = `${this.text("private_panel")} · Shizu`;
    document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = this.text(node.dataset.i18n); });
    for (const attribute of ["placeholder", "title", "aria-label"]) {
      document.querySelectorAll(`[data-i18n-${attribute}]`).forEach(node => {
        node.setAttribute(attribute, this.text(node.getAttribute(`data-i18n-${attribute}`)));
      });
    }
  }

  on(id, event, action) {
    this.element(id).addEventListener(event, async e => {
      e.preventDefault();
      const button = e.submitter || (e.target.closest ? e.target.closest("button") : null);
      if (button) button.disabled = true;
      try { await action(e); } catch (error) { this.toast(error.message, true); }
      finally { if (button) button.disabled = false; }
    });
  }

  bind() {
    this.on("login-button", "click", () => this.login());
    this.on("logout", "click", async () => {
      await this.api("/api/logout", { method: "POST" });
      this.lock();
      this.element("login-status").textContent = this.text("logged_out");
    });
    document.querySelectorAll("[data-view]").forEach(button => {
      button.addEventListener("click", () => this.showView(button.dataset.view).catch(error => this.toast(error.message, true)));
    });
    this.on("settings-form", "submit", async () => {
      await this.api("/api/settings", {
        method: "POST", json: {
          prefixes: this.element("prefixes").value.trim().split(/\s+/).filter(Boolean),
          language: this.element("language").value,
          api_protection: this.element("api-protection").checked,
        },
      });
      await this.translate();
      await this.refresh();
      this.toast(this.text("saved"));
    });
    this.on("refresh-modules", "click", () => this.refresh());
    this.element("module-search").addEventListener("input", () => this.renderModules());
    this.on("load-form", "submit", async () => {
      const result = await this.api("/api/modules/load", { method: "POST", json: { url: this.element("module-url").value.trim() } });
      this.element("module-url").value = "";
      await this.refresh();
      this.toast(result.message);
    });
    this.on("refresh-logs", "click", () => this.refreshLogs());
    this.on("log-level", "change", () => this.refreshLogs());
    this.on("download-logs", "click", () => {
      this.download(new Blob([this.element("log-output").textContent], { type: "text/plain;charset=utf-8" }), "shizu-logs.txt");
    });
    this.on("download-backup", "click", async () => {
      const archive = await this.api("/api/backups/download", { method: "POST", blob: true });
      this.download(archive, `shizu-${new Date().toISOString().replace(/[:.]/g, "-")}.shizu-backup`);
      this.toast(this.text("backup_created"));
    });
    this.on("auto-backup", "change", async () => {
      const input = this.element("auto-backup");
      try { await this.saveBackup("auto_backup", input.checked); }
      catch (error) { input.checked = !input.checked; throw error; }
    });
    this.on("backup-time-form", "submit", () => this.saveBackup("backup_time", this.element("backup-time").value));
    this.on("restore-form", "submit", () => this.inspectBackup());
    this.on("confirm-restore", "click", async () => {
      const result = await this.api("/api/backups/restore", { method: "POST", json: { preview_id: this.previewId } });
      this.element("restore-preview").hidden = true;
      this.previewId = null;
      this.toast(result.message);
      clearTimeout(this.logTimer);
      this.element("dashboard").inert = true;
      this.csrf = "";
      this.element("log-output").textContent = "";
    });
    for (const id of ["restore-file", "restore-legacy"]) {
      this.element(id).addEventListener("change", () => {
        this.previewId = null;
        this.element("restore-preview").hidden = true;
      });
    }
    this.on("close-config", "click", () => this.element("config-dialog").close());
    this.bindConfigBackdrop();
  }

  bindConfigBackdrop() {
    const dialog = this.element("config-dialog");
    let startedOutside = false;
    dialog.addEventListener("pointerdown", event => {
      startedOutside = this.isConfigBackdrop(event);
    });
    dialog.addEventListener("pointercancel", () => { startedOutside = false; });
    dialog.addEventListener("click", event => {
      if (startedOutside && this.isConfigBackdrop(event)) dialog.close();
      startedOutside = false;
    });
  }

  isConfigBackdrop(event) {
    const dialog = this.element("config-dialog");
    const bounds = dialog.getBoundingClientRect();
    return event.target === dialog && (
      event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom
    );
  }

  async start() {
    try {
      await this.translate();
      try {
        const session = await this.api("/api/session");
        this.csrf = session.csrf;
        await this.unlock();
      } catch (error) {
        if (error.status !== 401) throw error;
        this.lock();
        const pending = await this.api("/api/auth/status");
        if (pending.status === "approved") {
          this.csrf = pending.csrf;
          await this.unlock();
        } else if (pending.status === "pending") {
          this.waitForApproval(pending.code);
        }
      }
    } catch (error) {
      this.lock();
      this.element("login-status").textContent = error.message;
    } finally { this.element("boot").hidden = true; }
  }

  lock() {
    this.csrf = "";
    this.state = null;
    this.previewId = null;
    clearTimeout(this.authTimer);
    clearTimeout(this.logTimer);
    this.element("config-dialog").close();
    this.element("dashboard").hidden = true;
    this.element("login").hidden = false;
    this.element("login-code").hidden = true;
    this.element("login-button").hidden = false;
    this.element("login-button").disabled = !this.invite;
    this.element("login-status").textContent = this.invite ? "" : this.text("invite_needed");
    this.element("modules-list").replaceChildren();
    this.element("config-fields").replaceChildren();
    this.element("log-output").textContent = "";
    this.element("restore-file").value = "";
  }

  async login() {
    try {
      const result = await this.api("/api/auth/start", { method: "POST", json: { invite: this.invite } });
      this.invite = null;
      this.waitForApproval(result.code);
    } catch (error) {
      this.element("login-status").textContent = error.message;
      throw error;
    }
  }

  waitForApproval(code) {
    this.element("login-button").hidden = true;
    this.element("login-code").hidden = false;
    this.element("code-value").textContent = code;
    this.element("login-status").textContent = this.text("waiting_approval");
    this.authTimer = setTimeout(() => this.pollApproval(), 1500);
  }

  async pollApproval() {
    try {
      const result = await this.api("/api/auth/status");
      if (result.status === "approved") {
        this.csrf = result.csrf;
        await this.unlock();
      } else if (result.status === "pending") {
        this.authTimer = setTimeout(() => this.pollApproval(), 1500);
      } else {
        this.lock();
        this.element("login-status").textContent = this.text(result.status === "denied" ? "login_denied" : "invite_expired");
      }
    } catch (error) {
      this.element("login-status").textContent = error.message;
      this.authTimer = setTimeout(() => this.pollApproval(), 4000);
    }
  }

  async unlock() {
    await this.refresh();
    this.invite = null;
    this.element("login").hidden = true;
    this.element("dashboard").hidden = false;
    this.element("dashboard").inert = false;
    await this.showView("settings");
  }

  async refresh() {
    this.state = await this.api("/api/state");
    const { account, settings, backups } = this.state;
    this.element("account-name").textContent = account.name || account.username || String(account.id);
    this.element("account-id").textContent = account.username ? `@${account.username}` : String(account.id);
    this.element("prefixes").value = settings.prefixes.join(" ");
    this.element("language").value = settings.language;
    this.element("api-protection").checked = settings.api_protection;
    this.element("key-path").textContent = backups.key_path;
    this.renderModules();
  }

  async showView(name) {
    if (!this.csrf) return;
    if (this.view !== name) document.querySelector(".content").scrollTop = 0;
    this.view = name;
    document.querySelectorAll(".view").forEach(section => { section.hidden = section.id !== `view-${name}`; });
    document.querySelectorAll(".nav").forEach(button => {
      const active = button.dataset.view === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    clearTimeout(this.logTimer);
    if (name === "logs") await this.refreshLogs();
    if (name === "backups") await this.backupSettings();
  }

  node(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  action(text, className, callback) {
    const button = this.node("button", className, text);
    button.type = "button";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { await callback(); } catch (error) { this.toast(error.message, true); }
      finally { button.disabled = false; }
    });
    return button;
  }

  renderModules() {
    if (!this.state) return;
    const list = this.element("modules-list");
    list.replaceChildren();
    const query = this.element("module-search").value.toLocaleLowerCase();
    const modules = this.state.modules.filter(m => `${m.name} ${m.author} ${m.description}`.toLocaleLowerCase().includes(query));
    this.element("modules-empty").hidden = modules.length > 0;
    for (const module of modules) {
      const card = this.node("article", "module-card");
      const head = this.node("div", "module-head");
      head.append(this.node("h2", "", module.name), this.node("span", `badge${module.core ? "" : " external"}`, this.text(module.core ? "core_module" : "external_module")));
      const meta = this.node("div", "module-meta");
      meta.append(this.node("span", "", module.author), this.node("span", "", this.format("commands_count", module.commands)));
      const actions = this.node("div", "module-actions");
      if (module.config_count) actions.append(this.action(this.text("configure"), "button secondary", () => this.openConfig(module.name)));
      else actions.append(this.node("span", "small muted", this.text("no_configuration")));
      if (!module.core) actions.append(this.action(this.text("unload"), "text-button", async () => {
        if (!confirm(this.format("unload_confirm", module.name))) return;
        await this.api(`/api/modules/${encodeURIComponent(module.name)}/unload`, { method: "POST" });
        await this.refresh();
        this.toast(this.text("module_unloaded"));
      }));
      card.append(head, this.node("p", "", module.description), meta, actions);
      list.append(card);
    }
  }

  async openConfig(name) {
    const config = await this.api(`/api/modules/${encodeURIComponent(name)}/config`);
    this.element("config-title").textContent = config.name;
    const fields = this.element("config-fields");
    fields.replaceChildren();
    config.fields.forEach((field, index) => {
      const row = this.node("div", "config-field");
      const label = this.node("label", "", field.key);
      label.htmlFor = `config-input-${index}`;
      row.append(label, this.node("p", "", field.description));
      const action = this.node("div", "input-action");
      let input;
      if (field.choices && !field.hidden) {
        input = this.node("select");
        field.choices.forEach((value, i) => {
          const option = this.node("option", "", typeof value === "string" ? value : JSON.stringify(value));
          option.value = String(i);
          option.selected = JSON.stringify(value) === JSON.stringify(field.value);
          input.append(option);
        });
      } else if (field.type === "json" && !field.hidden) {
        input = this.node("textarea");
        input.value = JSON.stringify(field.value, null, 2);
      } else {
        input = this.node("input");
        input.type = field.hidden ? "password" : field.type === "boolean" ? "checkbox" : field.type === "number" ? "number" : "text";
        if (field.type === "boolean" && !field.hidden) input.checked = field.value;
        else input.value = field.hidden ? "" : String(field.value ?? "");
        if (field.type === "number") input.step = "any";
        input.autocomplete = "off";
      }
      input.id = `config-input-${index}`;
      input.disabled = !field.editable;
      const button = this.action(this.text("save"), "button primary", async () => {
        let value;
        if (field.hidden && !input.value) throw new Error(this.text("secret_empty"));
        try {
          if (field.choices && !field.hidden) value = field.choices[Number(input.value)];
          else if (field.type === "boolean") {
            if (field.hidden) value = JSON.parse(input.value);
            else value = input.checked;
          } else if (field.type === "json") value = JSON.parse(input.value);
          else if (field.type === "number") {
            if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error();
            value = Number(input.value);
          } else value = input.value;
        } catch { throw new Error(this.text("invalid_value")); }
        await this.api(`/api/modules/${encodeURIComponent(name)}/config`, { method: "POST", json: { key: field.key, value } });
        if (field.hidden) input.value = "";
        this.toast(this.text("saved"));
      });
      button.disabled = !field.editable;
      action.append(input, button);
      row.append(action);
      if (field.hidden) row.append(this.node("p", "hidden-hint", this.text(field.configured ? "secret_configured" : "secret_unset")));
      fields.append(row);
    });
    this.element("config-dialog").showModal();
  }

  async refreshLogs() {
    clearTimeout(this.logTimer);
    if (!this.csrf) return;
    const result = await this.api(`/api/logs?level=${encodeURIComponent(this.element("log-level").value)}`);
    const output = this.element("log-output");
    const atBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 50;
    output.textContent = result.lines.join("\n\n") || this.text("no_logs");
    if (atBottom) output.scrollTop = output.scrollHeight;
    if (this.view === "logs") this.logTimer = setTimeout(async () => {
      if (document.hidden) { this.logTimer = setTimeout(() => this.refreshLogs().catch(error => this.toast(error.message, true)), 6000); return; }
      try { await this.refreshLogs(); } catch (error) { this.toast(error.message, true); }
    }, 6000);
  }

  async backupSettings() {
    const available = this.state.modules.some(m => m.name === "ShizuBackuper");
    this.element("backup-schedule").hidden = !available;
    if (!available) return;
    const config = await this.api("/api/modules/ShizuBackuper/config");
    this.element("auto-backup").checked = config.fields.find(f => f.key === "auto_backup")?.value ?? false;
    this.element("backup-time").value = config.fields.find(f => f.key === "backup_time")?.value || "03:00";
  }

  async saveBackup(key, value) {
    await this.api("/api/modules/ShizuBackuper/config", { method: "POST", json: { key, value } });
    this.toast(this.text("saved"));
  }

  async inspectBackup() {
    this.element("restore-preview").hidden = true;
    this.previewId = null;
    const file = this.element("restore-file").files[0];
    if (!file) throw new Error(this.text("file_required"));
    if (file.size > this.state.backups.max_bytes) throw new Error(this.text("too_large"));
    const legacy = this.element("restore-legacy").checked ? "1" : "0";
    const result = await this.api(`/api/backups/inspect?legacy=${legacy}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    this.previewId = result.preview_id;
    this.element("restore-summary").textContent = this.format("restore_summary", file.name, result.sections, result.modules);
    this.element("restore-preview").hidden = false;
  }

  download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = this.node("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  toast(message, error = false) {
    const toast = this.element("toast");
    clearTimeout(this.toastTimer);
    toast.textContent = message;
    toast.classList.toggle("error", error);
    toast.hidden = false;
    this.toastTimer = setTimeout(() => { toast.hidden = true; }, error ? 8000 : 5000);
  }

}

new ShizuPanel().start();
