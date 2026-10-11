"use strict";

class ShizuPanel {
  constructor() {
    this.strings = {};
    this.csrf = "";
    this.state = null;
    this.invite = new URLSearchParams(location.hash.slice(1)).get("invite");
    history.replaceState(null, "", location.pathname);
    this.view = "overview";
    this.previewId = null;
    this.authTimer = null;
    this.logTimer = null;
    this.toastTimer = null;
    this.moduleGroups = { external: true, core: false };
    this.viewScroll = {};
    this.overviewEpoch = 0;
    this.metricsEpoch = 0;
    this.metricsTimer = null;
    this.diagnosticsEpoch = 0;
    this.permissionsEpoch = 0;
    this.permissionsData = null;
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
    const avatar = this.element("account-avatar");
    avatar.addEventListener("load", () => { avatar.hidden = false; });
    avatar.addEventListener("error", () => { avatar.hidden = true; });
    this.on("header-refresh", "click", async () => {
      if (["overview", "modules", "settings", "backups"].includes(this.view)) await this.refresh();
      if (this.view === "overview") await Promise.all([this.refreshOverviewEvents(), this.refreshMetrics()]);
      if (this.view === "server") await Promise.all([this.refreshMetrics(), this.refreshDiagnostics()]);
      if (this.view === "permissions") await this.refreshPermissions();
      if (this.view === "logs") await this.refreshLogs();
      if (this.view === "backups") await this.backupSettings();
    });
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
    this.on("refresh-overview", "click", async () => {
      await this.refresh();
      await Promise.all([this.refreshOverviewEvents(), this.refreshMetrics()]);
    });
    this.on("overview-install", "click", async () => {
      await this.showView("modules");
      document.querySelector(".module-install").open = true;
      this.element("module-url").focus();
    });
    this.on("overview-backup", "click", () => this.downloadBackup());
    this.on("refresh-server", "click", () => Promise.all([this.refreshMetrics(), this.refreshDiagnostics()]));
    this.on("refresh-permissions", "click", () => this.refreshPermissions());
    this.element("permissions-search").addEventListener("input", () => this.renderPermissions());
    document.addEventListener("visibilitychange", () => {
      clearTimeout(this.metricsTimer);
      this.metricsEpoch++;
      if (!document.hidden) this.refreshMetrics();
    });
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
    this.on("download-backup", "click", () => this.downloadBackup());
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
      clearTimeout(this.metricsTimer);
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
    this.on("back-to-modules", "click", async () => {
      await this.showView("modules");
      if (this.configTrigger?.isConnected) this.configTrigger.focus({ preventScroll: true });
    });
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
    clearTimeout(this.metricsTimer);
    this.viewScroll = {};
    this.overviewEpoch++;
    this.metricsEpoch++;
    this.diagnosticsEpoch++;
    this.permissionsEpoch++;
    this.permissionsData = null;
    this.configTrigger = null;
    this.element("dashboard").hidden = true;
    this.element("login").hidden = false;
    this.element("login-code").hidden = true;
    this.element("login-button").hidden = false;
    this.element("login-button").disabled = !this.invite;
    this.element("login-status").textContent = this.invite ? "" : this.text("invite_needed");
    this.element("modules-list").replaceChildren();
    this.element("config-fields").replaceChildren();
    this.element("log-output").textContent = "";
    this.element("overview-events").replaceChildren();
    this.element("overview-history").replaceChildren();
    this.element("account-avatar").hidden = true;
    this.element("account-avatar").removeAttribute("src");
    for (const id of ["overview-resources", "server-resources", "server-process", "server-versions", "server-database", "server-files", "permissions-users", "permissions-groups"]) this.element(id).replaceChildren();
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
    await this.showView("overview");
  }

  async refresh() {
    this.state = await this.api("/api/state");
    const { account, settings, backups } = this.state;
    this.element("account-name").textContent = account.name || account.username || String(account.id);
    this.element("account-id").textContent = account.username ? `@${account.username}` : String(account.id);
    const avatar = this.element("account-avatar");
    if (account.has_avatar) {
      if (!avatar.hasAttribute("src")) avatar.src = "/api/avatar";
    } else {
      avatar.hidden = true;
      avatar.removeAttribute("src");
    }
    this.element("prefixes").value = settings.prefixes.join(" ");
    this.element("language").value = settings.language;
    this.element("api-protection").checked = settings.api_protection;
    this.element("key-path").textContent = backups.key_path;
    this.renderModules();
    this.renderOverview();
  }

  async showView(name) {
    if (!this.csrf) return;
    const content = document.querySelector(".content");
    const previous = this.view;
    if (previous !== name) this.viewScroll[previous] = content.scrollTop;
    this.view = name;
    this.updateHeading();
    document.querySelectorAll(".view").forEach(section => { section.hidden = section.id !== `view-${name}`; });
    document.querySelectorAll(".nav").forEach(button => {
      const active = button.dataset.view === (name === "config" ? "modules" : name);
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
      if (active) button.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    if (previous !== name) content.scrollTop = this.viewScroll[name] || 0;
    clearTimeout(this.logTimer);
    clearTimeout(this.metricsTimer);
    this.metricsEpoch++;
    if (name === "overview") await Promise.all([this.refreshOverviewEvents(), this.refreshMetrics()]);
    if (name === "server") await Promise.all([this.refreshMetrics(), this.refreshDiagnostics()]);
    if (name === "permissions") await this.refreshPermissions();
    if (name === "logs") await this.refreshLogs();
    if (name === "backups") await this.backupSettings();
  }

  renderOverview() {
    if (!this.state) return;
    const { settings, modules, backups } = this.state;
    this.updateHeading();
    this.element("overview-prefixes").textContent = settings.prefixes.join(" ");
    this.element("overview-language").textContent = this.element("language").selectedOptions[0]?.textContent || settings.language;
    this.element("overview-protection").textContent = this.text(settings.api_protection ? "enabled" : "disabled");
    this.element("overview-protection").classList.toggle("summary-warning", !settings.api_protection);
    this.element("overview-bot").textContent = settings.bot ? `@${settings.bot.replace(/^@/, "")}` : this.text("not_configured");
    const available = backups.available ?? modules.some(module => module.name === "ShizuBackuper");
    this.element("overview-backup-status").textContent = this.text(!available ? "backup_unavailable" : backups.auto_backup ? "enabled" : "disabled");
    this.element("overview-backup-time").textContent = available && backups.auto_backup ? this.format("backup_schedule_summary", backups.backup_time) : this.text("quick_backup_hint");
  }

  updateHeading() {
    this.element("page-title").textContent = this.text(this.view === "config" ? "module_configuration" : `${this.view}_title`);
    this.element("header-refresh").hidden = ["config", "settings"].includes(this.view);
    const subtitle = this.element("page-subtitle");
    subtitle.textContent = this.view === "overview" && this.state
      ? this.format("overview_subtitle", this.state.runtime?.version || "—", this.state.modules.length, this.state.modules.reduce((total, module) => total + module.commands, 0))
      : "";
    subtitle.hidden = !subtitle.textContent;
  }

  formatUptime(value) {
    if (!Number.isFinite(value)) return "—";
    const minutes = Math.max(0, Math.floor(value / 60));
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor(minutes / 60) % 24;
    if (days) return this.format("uptime_days", days, hours);
    if (hours) return this.format("uptime_hours", hours, minutes % 60);
    return this.format("uptime_minutes", minutes);
  }

  async refreshOverviewEvents() {
    if (!this.csrf) return;
    const epoch = ++this.overviewEpoch;
    const status = this.element("overview-events-status");
    const list = this.element("overview-events");
    status.textContent = this.text("events_loading");
    try {
      const result = await this.api("/api/logs?level=INFO");
      if (!this.csrf || epoch !== this.overviewEpoch) return;
      list.replaceChildren();
      result.lines.slice(-5).reverse().forEach(line => {
        const item = this.node("li", "event-row");
        if (/\b(ERROR|CRITICAL)\b/.test(line)) item.classList.add("event-error");
        else if (/\bWARNING\b/.test(line)) item.classList.add("event-warning");
        const level = line.match(/\b(INFO|WARNING|ERROR|CRITICAL|DEBUG)\b/)?.[1] || "INFO";
        const source = line.match(/\b(shizu[\w.]*)\s*:/)?.[1];
        const icon = this.node("span", "event-icon", level === "WARNING" || level === "ERROR" || level === "CRITICAL" ? "!" : "i");
        icon.setAttribute("aria-hidden", "true");
        const info = this.node("div", "event-info");
        info.append(this.node("strong", "", source || this.text("recent_events")), this.node("p", "event-message", (source ? line.slice(line.indexOf(source) + source.length + 1).trim() : line).slice(0, 1200)));
        item.append(icon, info, this.node("span", "event-level", level));
        list.append(item);
      });
      status.textContent = result.lines.length ? "" : this.text("no_logs");
    } catch (error) {
      if (!this.csrf || epoch !== this.overviewEpoch) return;
      list.replaceChildren();
      status.textContent = error.message;
    }
  }

  async downloadBackup() {
    const archive = await this.api("/api/backups/download", { method: "POST", blob: true });
    this.download(archive, `shizu-${new Date().toISOString().replace(/[:.]/g, "-")}.shizu-backup`);
    this.toast(this.text("backup_created"));
    if (this.view === "overview") await this.refreshOverviewEvents();
  }

  bytes(value) {
    if (!Number.isFinite(value)) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    const index = value > 0 ? Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1) : 0;
    return `${new Intl.NumberFormat(document.documentElement.lang, { maximumFractionDigits: index ? 1 : 0 }).format(value / 1024 ** index)} ${units[index]}`;
  }

  percentage(value) {
    return Number.isFinite(value) ? `${new Intl.NumberFormat(document.documentElement.lang, { maximumFractionDigits: 1 }).format(value)}%` : "—";
  }

  summary(container, label, value) {
    const row = this.node("div");
    row.append(this.node("dt", "", label), this.node("dd", "", value));
    container.append(row);
  }

  resourceCards(container, data, compact = false) {
    container.replaceChildren();
    const readings = [
      ["cpu_title", data.cpu_percent, this.format("cpu_cores", data.cpu_count ?? "—")],
      ["ram_title", data.memory?.percent, data.memory ? `${this.bytes(data.memory.used)} / ${this.bytes(data.memory.total)}` : "—"],
      ["disk_title", data.disk?.percent, data.disk ? this.format("disk_free", this.bytes(data.disk.free), this.bytes(data.disk.total)) : "—"],
    ];
    if (compact) readings.push(
      ["process_memory", data.memory?.total && Number.isFinite(data.process.memory) ? data.process.memory / data.memory.total * 100 : null, "", this.bytes(data.process.memory)],
      ["swap_title", data.swap?.percent, ""],
    );
    for (const [key, value, detail, display] of readings) {
      const card = this.node("div", compact ? "compact-resource" : "surface resource-card");
      const heading = this.node("div", "surface-heading");
      heading.append(this.node(compact ? "span" : "h2", "", this.text(key)), this.node("strong", "", display || this.percentage(value)));
      card.append(heading);
      if (Number.isFinite(value)) {
        const meter = this.node("progress", "resource-meter");
        meter.max = 100; meter.value = Math.max(0, Math.min(100, value));
        meter.setAttribute("aria-label", this.text(key));
        card.append(meter);
      }
      if (!compact) card.append(this.node("p", "small muted", detail));
      container.append(card);
    }
  }

  async refreshMetrics() {
    clearTimeout(this.metricsTimer);
    if (!this.csrf || !["overview", "server"].includes(this.view) || document.hidden) return;
    const epoch = ++this.metricsEpoch;
    try {
      const data = await this.api("/api/server/metrics");
      if (!this.csrf || epoch !== this.metricsEpoch) return;
      this.resourceCards(this.element("overview-resources"), data, true);
      this.resourceCards(this.element("server-resources"), data);
      const process = this.element("server-process");
      process.replaceChildren();
      this.summary(process, this.text("process_memory"), this.bytes(data.process.memory));
      this.summary(process, this.text("process_threads"), data.process.threads ?? "—");
      this.summary(process, this.text("host_uptime"), this.formatUptime(data.host_uptime));
      this.summary(process, this.text("uptime_title"), this.formatUptime(data.shizu_uptime));
      this.summary(process, this.text("load_average"), data.load_average ? data.load_average.map(n => n.toFixed(2)).join(" / ") : "—");
      this.renderHistory(data.history || []);
      const time = new Date(data.sampled_at * 1000).toLocaleTimeString(document.documentElement.lang);
      for (const id of ["overview-metrics-status", "server-metrics-status"]) this.element(id).textContent = this.format("metrics_updated", time);
    } catch (error) {
      if (!this.csrf || epoch !== this.metricsEpoch) return;
      for (const id of ["overview-metrics-status", "server-metrics-status"]) this.element(id).textContent = error.message;
    } finally {
      if (this.csrf && epoch === this.metricsEpoch && ["overview", "server"].includes(this.view) && !document.hidden) this.metricsTimer = setTimeout(() => this.refreshMetrics(), 5000);
    }
  }

  renderHistory(history) {
    const chart = this.element("overview-history");
    chart.replaceChildren();
    const values = history.filter(Number.isFinite).slice(-24);
    values.forEach((value, index) => {
      const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      const height = Math.max(2, Math.min(100, Math.max(0, value)) * 0.6);
      bar.setAttribute("x", index * 21.4);
      bar.setAttribute("y", 60 - height);
      bar.setAttribute("width", "16");
      bar.setAttribute("height", height);
      bar.setAttribute("fill", index === values.length - 1 ? "#157aff" : "#c5ddf0");
      chart.append(bar);
    });
  }

  async refreshDiagnostics() {
    const epoch = ++this.diagnosticsEpoch;
    const status = this.element("server-diagnostics-status");
    status.textContent = this.text("data_loading");
    try {
      const data = await this.api("/api/server/diagnostics");
      if (!this.csrf || epoch !== this.diagnosticsEpoch) return;
      const versions = this.element("server-versions");
      versions.replaceChildren();
      this.summary(versions, "Shizu", this.state.runtime?.version || "—");
      this.summary(versions, "Python", data.python);
      this.summary(versions, this.text("operating_system"), data.system);
      this.summary(versions, this.text("architecture"), data.architecture);
      for (const [name, value] of Object.entries(data.packages)) this.summary(versions, name, value || "—");
      const db = data.files.find(file => file.kind === "database");
      const info = this.element("server-database");
      info.replaceChildren();
      this.summary(info, this.text("database_sections"), data.database_sections);
      this.summary(info, this.text("file_state"), this.text(`file_${db?.status || "unavailable"}`));
      this.summary(info, this.text("file_size"), this.bytes(db?.bytes));
      if (db?.status === "present") this.summary(info, this.text("file_access"), this.text(db.readable && db.writable ? "file_read_write" : db.readable ? "file_read_only" : "file_no_access"));
      const files = this.element("server-files");
      files.replaceChildren();
      for (const file of data.files) {
        const row = this.node("article", "file-row");
        const heading = this.node("div", "file-heading");
        heading.append(this.node("strong", "", this.text(file.kind)), this.node("code", "muted", file.name || "—"));
        const details = this.node("div", "file-details");
        details.append(this.node("span", "", this.text(`file_${file.status}`)));
        if (file.status === "present") {
          details.append(this.node("span", "", this.bytes(file.bytes)), this.node("code", file.private ? "permission-badge" : "permission-badge restricted", file.mode));
          details.append(this.node("span", "small muted", this.format("file_modified", new Date(file.modified * 1000).toLocaleString(document.documentElement.lang))));
        }
        row.append(heading, details); files.append(row);
      }
      status.textContent = "";
    } catch (error) {
      if (this.csrf && epoch === this.diagnosticsEpoch) status.textContent = error.message;
    }
  }

  async refreshPermissions() {
    const epoch = ++this.permissionsEpoch;
    const status = this.element("permissions-status");
    status.textContent = this.text("data_loading");
    try {
      const data = await this.api("/api/permissions");
      if (!this.csrf || epoch !== this.permissionsEpoch) return;
      this.permissionsData = data;
      this.renderPermissions();
      status.textContent = "";
    } catch (error) {
      if (this.csrf && epoch === this.permissionsEpoch) status.textContent = error.message;
    }
  }

  commandChips(commands, checkGrant = true) {
    const chips = this.node("div", "permission-chips");
    const prefix = this.state.settings.prefixes[0] || ".";
    for (const command of commands) {
      const chip = this.node("span", "permission-badge", `${prefix}${command.name}`);
      if (!command.available || (checkGrant && !command.grant_applies)) {
        chip.classList.add("restricted");
        const reason = this.text(command.available ? "command_conditions" : "command_not_loaded");
        chip.append(this.node("small", "", reason));
      }
      if (command.module) chip.title = command.module;
      chips.append(chip);
    }
    return chips;
  }

  renderPermissions() {
    if (!this.permissionsData || !this.state) return;
    const data = this.permissionsData;
    this.element("permissions-owner-mode").textContent = this.text(data.owner_mode ? "enabled" : "disabled");
    const query = this.element("permissions-search").value.trim().toLocaleLowerCase();
    const users = data.users.filter(user => `${user.id} ${user.account_owner ? this.state.account.name : ""} ${user.groups.join(" ")} ${user.commands.map(c => c.name).join(" ")}`.toLocaleLowerCase().includes(query));
    const list = this.element("permissions-users");
    list.replaceChildren();
    for (const user of users) {
      const card = this.node("article", "surface permission-user");
      const heading = this.node("div", "surface-heading");
      const title = this.node("div");
      title.append(this.node("h3", "", user.account_owner ? this.state.account.name || user.id : this.format("telegram_user", user.id)), this.node("code", "small muted", `ID ${user.id}`));
      heading.append(title);
      if (user.account_owner || user.additional_owner) heading.append(this.node("span", `permission-badge${user.owner_active ? "" : " restricted"}`, this.text(user.account_owner ? "account_owner" : user.owner_active ? "additional_owner" : "owner_inactive")));
      card.append(heading);
      if (user.account_owner) card.append(this.node("p", "small muted permission-note", this.text("account_owner_scope")));
      card.append(this.node("h4", "", this.text("personal_grants")));
      card.append(user.direct.length ? this.commandChips(user.direct) : this.node("p", "small muted", this.text("no_direct_grants")));
      if (user.groups.length) {
        card.append(this.node("h4", "", this.text("assigned_groups")));
        const groups = this.node("div", "permission-chips");
        for (const name of user.groups) groups.append(this.node("span", "permission-badge", name));
        card.append(groups);
        const inherited = user.commands.filter(command => !user.direct.some(item => item.name === command.name));
        if (inherited.length) { card.append(this.node("h4", "", this.text("group_commands")), this.commandChips(inherited)); }
      }
      list.append(card);
    }
    this.element("permissions-empty").hidden = users.length > 0;
    const groups = data.groups.filter(group => `${group.name} ${group.users.join(" ")} ${group.commands.map(c => c.name).join(" ")}`.toLocaleLowerCase().includes(query));
    const groupList = this.element("permissions-groups");
    groupList.replaceChildren();
    for (const group of groups) {
      const card = this.node("details", "surface permission-group");
      const heading = this.node("summary", "surface-heading");
      heading.append(this.node("strong", "", group.name), this.node("span", "small muted", this.format("group_users_count", group.users.length)));
      card.append(heading, this.commandChips(group.commands, false));
      card.append(this.node("p", "small muted permission-note", group.users.length ? group.users.join(", ") : this.text("group_no_users")));
      groupList.append(card);
    }
    this.element("permissions-groups-empty").hidden = groups.length > 0;
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
    const query = this.element("module-search").value.trim().toLocaleLowerCase();
    const modules = this.state.modules.filter(m => `${m.name} ${m.author} ${m.description}`.toLocaleLowerCase().includes(query));
    this.element("modules-empty").hidden = modules.length > 0;
    for (const group of ["external", "core"]) {
      const items = modules.filter(module => Boolean(module.core) === (group === "core"));
      if (query && !items.length) continue;
      const section = this.node("details", `module-group ${group}`);
      section.dataset.group = group;
      section.open = Boolean(query) || this.moduleGroups[group];
      const heading = this.node("summary", "module-group-heading");
      heading.append(this.node("h2", "", this.text(`${group}_modules`)), this.node("span", "group-count", items.length));
      section.append(heading);
      const rows = this.node("div", "module-rows");
      items.sort((a, b) => a.name.localeCompare(b.name)).forEach(module => rows.append(this.moduleCard(module)));
      if (!items.length) rows.append(this.node("p", "group-empty muted", this.text("no_modules")));
      section.append(rows);
      section.addEventListener("toggle", () => {
        if (!this.element("module-search").value.trim()) this.moduleGroups[group] = section.open;
      });
      list.append(section);
    }
  }

  moduleCard(module) {
    const card = this.node("article", "module-card");
    const icon = this.node("span", "module-icon", module.name.slice(0, 2).toUpperCase());
    icon.setAttribute("aria-hidden", "true");
    const info = this.node("div", "module-info");
    const meta = this.node("div", "module-meta");
    meta.append(this.node("span", "", module.author), this.node("span", "", this.format("commands_count", module.commands)));
    info.append(this.node("h3", "", module.name), this.node("p", "", module.description), meta);
    const actions = this.node("div", "module-actions");
    if (module.config_count) actions.append(this.action(this.text("configure"), "button secondary", () => this.openConfig(module.name)));
    else actions.append(this.node("span", "small muted", this.text("no_configuration")));
    if (!module.core) actions.append(this.action(this.text("unload"), "text-button", async () => {
      if (!confirm(this.format("unload_confirm", module.name))) return;
      await this.api(`/api/modules/${encodeURIComponent(module.name)}/unload`, { method: "POST" });
      await this.refresh();
      this.toast(this.text("module_unloaded"));
    }));
    card.append(icon, info, actions);
    return card;
  }

  async openConfig(name) {
    this.configTrigger = document.activeElement;
    const config = await this.api(`/api/modules/${encodeURIComponent(name)}/config`);
    if (!this.csrf || this.view !== "modules") return;
    this.element("config-title").textContent = config.name;
    const fields = this.element("config-fields");
    fields.replaceChildren();
    config.fields.forEach((field, index) => {
      const row = this.node("div", "config-field");
      const label = this.node("label", "", field.label || field.key);
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
        if (name === "ShizuBackuper") this.updateBackupSummary(field.key, value);
        if (field.hidden) input.value = "";
        this.toast(this.text("saved"));
      });
      button.disabled = !field.editable;
      action.append(input, button);
      row.append(action);
      if (field.hidden) row.append(this.node("p", "hidden-hint", this.text(field.configured ? "secret_configured" : "secret_unset")));
      fields.append(row);
    });
    this.viewScroll.config = 0;
    await this.showView("config");
    this.element("config-title").focus({ preventScroll: true });
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
    this.updateBackupSummary(key, value);
    this.toast(this.text("saved"));
  }

  updateBackupSummary(key, value) {
    if (!this.state || !["auto_backup", "backup_time"].includes(key)) return;
    this.state.backups[key] = value;
    this.renderOverview();
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
