const STATUS_LABEL = {
  connecting: "Connecting...",
  connected: "Connected",
  disconnected: "Disconnected",
};

// A "group" is one tab-strip entry. It holds 1-4 panes (splits); each pane
// is its own xterm.js instance + paramiko session, tracked by session id.
const tabsManager = {
  groups: new Map(), // groupId -> { name, paneOrder: [sessionId,...] }
  panes: new Map(), // sessionId -> { groupId, profileId, profileName, term, fitAddon, container, statusText, reconnectBtn, state }
  activeGroupId: null,
  focusedPaneId: null,
  profiles: [],
  broadcastEnabled: false,
  splitLock: new Set(), // groupIds currently mid-split - blocks a double-click race

  init() {
    document.getElementById("profile-search").addEventListener("input", (e) => this.renderProfileList(e.target.value));
    document.getElementById("split-btn").addEventListener("click", () => this.splitActiveGroup());
    document.getElementById("broadcast-btn").addEventListener("click", () => this.toggleBroadcast());
    new ResizeObserver(() => this.applyActiveLayout()).observe(document.getElementById("terminal-area"));
    this.renderTabStrip();
    window.pywebview.api.get_app_version().then((v) => {
      document.getElementById("app-version").textContent = `v${v}`;
    });
    this.refreshProfiles().then(() => this.restoreLastSession());
  },

  async refreshProfiles() {
    this.profiles = await window.pywebview.api.list_profiles();
    this.renderProfileList(document.getElementById("profile-search").value);
  },

  async restoreLastSession() {
    window.pywebview.api.log_event("system", "Starting to load");
    const profiles = await window.pywebview.api.get_last_session();
    const emptyText = document.getElementById("empty-state-text");
    const spinner = document.getElementById("empty-state-spinner");

    if (profiles.length === 0) {
      emptyText.textContent = "Select a profile to connect, or create a new one.";
      spinner.classList.add("hidden");
      window.pywebview.api.log_event("system", "Loading done");
      return;
    }

    for (let i = 0; i < profiles.length; i++) {
      emptyText.textContent = `Restoring session ${i + 1} of ${profiles.length}...`;
      await this.openProfile(profiles[i]);
      // createPane() below does real synchronous work (a new xterm.js
      // Terminal instance, DOM insertion, fitAddon.fit()) that can otherwise
      // run back-to-back for every restored pane with no gap for the
      // browser to repaint or process input - on a slow first launch (e.g.
      // antivirus scanning a freshly (re)installed exe) that reads as the
      // window going "Not Responding" instead of visibly loading.
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
    emptyText.textContent = "Select a profile to connect, or create a new one.";
    spinner.classList.add("hidden");
    window.pywebview.api.log_event("system", "Loading done");
  },

  toggleBroadcast() {
    this.broadcastEnabled = !this.broadcastEnabled;
    document.getElementById("broadcast-btn").classList.toggle("active", this.broadcastEnabled);
  },

  renderProfileList(filter) {
    const list = document.getElementById("profile-list");
    list.innerHTML = "";
    const needle = (filter || "").toLowerCase();

    const filtered = this.profiles.filter(
      (p) => p.name.toLowerCase().includes(needle) || p.host.toLowerCase().includes(needle),
    );

    for (const profile of filtered) {
      const card = document.createElement("div");
      card.className = "profile-card";
      if (profile.env_color) card.classList.add(`env-${profile.env_color}`);

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = profile.name;

      const detail = document.createElement("span");
      detail.className = "detail";
      detail.textContent = `${profile.user}@${profile.host}:${profile.port}`;

      const transfer = document.createElement("button");
      transfer.className = "delete-btn transfer-btn";
      transfer.textContent = "⇅";
      transfer.title = "File transfer";
      transfer.addEventListener("click", (e) => {
        e.stopPropagation();
        transferPanel.open(profile);
      });

      const edit = document.createElement("button");
      edit.className = "delete-btn edit-btn";
      edit.textContent = "✎";
      edit.title = "Edit connection";
      edit.addEventListener("click", (e) => {
        e.stopPropagation();
        wizard.open(profile);
      });

      const del = document.createElement("button");
      del.className = "delete-btn";
      del.textContent = "×";
      del.title = "Delete profile";
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete profile "${profile.name}"?`)) return;
        await window.pywebview.api.delete_profile(profile.id);
        this.refreshProfiles();
      });

      card.appendChild(name);
      card.appendChild(detail);
      card.appendChild(transfer);
      card.appendChild(edit);
      card.appendChild(del);
      card.addEventListener("click", () => this.openProfile(profile));

      list.appendChild(card);
    }
  },

  // --- opening / splitting -------------------------------------------------

  async openProfile(profile) {
    const groupId = crypto.randomUUID();
    this.groups.set(groupId, { name: profile.name, paneOrder: [] });
    const sessionId = await this.openPaneInGroup(groupId, profile);
    if (!sessionId) {
      this.groups.delete(groupId);
      return;
    }
    this.renderTabStrip();
    this.switchGroup(groupId);
  },

  async splitActiveGroup() {
    if (!this.activeGroupId) return;
    const group = this.groups.get(this.activeGroupId);
    if (!group || group.paneOrder.length >= 4) return;

    // openPaneInGroup() awaits a network round-trip before paneOrder.push()
    // actually runs, so a second click during that gap would read the same
    // stale length and pass the cap check too - clicking Split twice fast
    // was landing 5 panes in a 4-pane grid. Lock synchronously, before the
    // await, so a second click while one is in flight is rejected outright.
    if (this.splitLock.has(this.activeGroupId)) return;
    this.splitLock.add(this.activeGroupId);
    document.getElementById("split-btn").disabled = true;

    try {
      const firstPane = this.panes.get(group.paneOrder[0]);
      const profile = this.profiles.find((p) => p.id === firstPane?.profileId);
      if (!profile) return;

      await this.openPaneInGroup(this.activeGroupId, profile);
      this.applyActiveLayout();
    } finally {
      this.splitLock.delete(this.activeGroupId);
      this.renderTabStrip();
    }
  },

  async openPaneInGroup(groupId, profile) {
    const result = await window.pywebview.api.open_session(profile.id, 120, 32);
    if (!result.ok) {
      alert(`Could not open session: ${result.error}`);
      return null;
    }
    const sessionId = result.session_id;
    this.createPane(sessionId, groupId, profile);
    this.groups.get(groupId).paneOrder.push(sessionId);
    return sessionId;
  },

  createPane(sessionId, groupId, profile) {
    document.getElementById("empty-state").classList.add("hidden");

    const container = document.createElement("div");
    container.className = "terminal-pane";
    container.dataset.sessionId = sessionId;

    const statusBar = document.createElement("div");
    statusBar.className = "pane-status-bar";
    const statusText = document.createElement("span");
    statusText.className = "status-text";
    statusText.textContent = STATUS_LABEL.connecting;
    const reconnectBtn = document.createElement("button");
    reconnectBtn.className = "reconnect-btn";
    reconnectBtn.textContent = "Reconnect";
    reconnectBtn.style.display = "none";
    reconnectBtn.addEventListener("click", () => this.reconnect(sessionId));

    // Grouped into one pill (shared border, no gap between them) instead of
    // two separate buttons floating apart - and plain text instead of the
    // ⎘/⎙ glyphs, which didn't render reliably (⎙ was showing as a padlock).
    const clipboardGroup = document.createElement("div");
    clipboardGroup.className = "pane-clipboard-group";

    const copyBtn = document.createElement("button");
    copyBtn.className = "clipboard-btn";
    copyBtn.textContent = "Copy";
    copyBtn.title = "Copy selection";
    copyBtn.addEventListener("click", () => this.copyFromPane(sessionId));

    const pasteBtn = document.createElement("button");
    pasteBtn.className = "clipboard-btn";
    pasteBtn.textContent = "Paste";
    pasteBtn.title = "Paste";
    pasteBtn.addEventListener("click", () => this.pasteIntoPane(sessionId));

    clipboardGroup.appendChild(copyBtn);
    clipboardGroup.appendChild(pasteBtn);

    const closeBtn = document.createElement("button");
    closeBtn.className = "reconnect-btn";
    closeBtn.textContent = "×";
    closeBtn.title = "Close pane";
    closeBtn.addEventListener("click", () => this.closePane(sessionId));
    statusBar.appendChild(statusText);
    statusBar.appendChild(reconnectBtn);
    statusBar.appendChild(clipboardGroup);
    statusBar.appendChild(closeBtn);

    const xtermHost = document.createElement("div");
    xtermHost.className = "xterm-host";

    container.appendChild(statusBar);
    container.appendChild(xtermHost);
    container.addEventListener("mousedown", () => this.setFocusedPane(sessionId));
    document.getElementById("terminal-area").appendChild(container);

    const term = new Terminal({
      convertEol: false,
      fontFamily: '"Cascadia Mono", Consolas, monospace',
      fontSize: 13,
      theme: {
        background: "#1c2430",
        foreground: "#e6edf3",
        cursor: "#4e87f6",
        selectionBackground: "#2a3441",
      },
      cursorBlink: true,
      scrollback: 5000,
      allowProposedApi: true,
    });
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(xtermHost);

    // navigator.clipboard.readText() hangs forever in this app's WebView2
    // context (no permission-prompt UI ever appears to resolve it), so
    // xterm's own Ctrl+V/Ctrl+C handling - which goes through that same API
    // - never completes either. Route both through the Python/OS clipboard
    // bridge instead (see Api.get_clipboard/set_clipboard in main.py).
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown") return true;
      const combo = (event.ctrlKey || event.metaKey) && !event.altKey;
      if (combo && event.key.toLowerCase() === "v") {
        this.pasteIntoPane(sessionId);
        return false;
      }
      if (combo && event.key.toLowerCase() === "c" && term.hasSelection()) {
        this.copyFromPane(sessionId);
        return false;
      }
      return true;
    });

    term.onData((data) => {
      window.pywebview.api.send_input(sessionId, data);
      if (this.broadcastEnabled) {
        const group = this.groups.get(groupId);
        if (group) {
          for (const siblingId of group.paneOrder) {
            if (siblingId !== sessionId) window.pywebview.api.send_input(siblingId, data);
          }
        }
      }
    });

    this.panes.set(sessionId, {
      groupId,
      profileId: profile.id,
      profileName: profile.name,
      term,
      fitAddon,
      container,
      statusText,
      reconnectBtn,
      state: "connecting",
    });
  },

  // --- tab strip / layout ---------------------------------------------------

  renderTabStrip() {
    const strip = document.getElementById("tab-strip-scroll");
    strip.innerHTML = "";
    for (const [groupId, group] of this.groups) {
      const el = document.createElement("div");
      el.className = "tab" + (groupId === this.activeGroupId ? " active" : "");

      const worst = this.groupState(groupId);
      const dot = document.createElement("span");
      dot.className = "status-dot " + worst;

      const label = document.createElement("span");
      label.textContent = group.paneOrder.length > 1 ? `${group.name} (×${group.paneOrder.length})` : group.name;

      const closeBtn = document.createElement("button");
      closeBtn.className = "tab-close";
      closeBtn.textContent = "×";
      closeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.closeGroup(groupId);
      });

      el.appendChild(dot);
      el.appendChild(label);
      el.appendChild(closeBtn);
      el.addEventListener("click", () => this.switchGroup(groupId));

      strip.appendChild(el);
    }

    const splitBtn = document.getElementById("split-btn");
    const activeGroup = this.groups.get(this.activeGroupId);
    splitBtn.style.display = activeGroup && activeGroup.paneOrder.length < 4 ? "" : "none";
    splitBtn.disabled = this.splitLock.has(this.activeGroupId);
  },

  groupState(groupId) {
    const group = this.groups.get(groupId);
    if (!group) return "disconnected";
    const states = group.paneOrder.map((sid) => this.panes.get(sid)?.state);
    if (states.includes("disconnected")) return "disconnected";
    if (states.includes("connecting")) return "connecting";
    return "connected";
  },

  switchGroup(groupId) {
    this.activeGroupId = groupId;
    const group = this.groups.get(groupId);
    this.focusedPaneId = group ? group.paneOrder[0] : null;
    this.renderTabStrip();
    this.applyActiveLayout();
  },

  setFocusedPane(sessionId) {
    this.focusedPaneId = sessionId;
    for (const [sid, pane] of this.panes) {
      pane.container.classList.toggle("focused", sid === sessionId && this.groups.get(pane.groupId)?.paneOrder.length > 1);
    }
    const pane = this.panes.get(sessionId);
    if (pane) pane.term.focus();
  },

  applyActiveLayout() {
    const area = document.getElementById("terminal-area");
    const group = this.groups.get(this.activeGroupId);

    for (const [sid, pane] of this.panes) {
      pane.container.style.display = pane.groupId === this.activeGroupId ? "flex" : "none";
      pane.container.style.gridColumn = "";
      pane.container.style.gridRow = "";
    }

    if (!group) return;
    const n = group.paneOrder.length;

    if (n <= 1) {
      area.style.gridTemplateColumns = "1fr";
      area.style.gridTemplateRows = "1fr";
    } else if (n === 2) {
      area.style.gridTemplateColumns = "1fr 1fr";
      area.style.gridTemplateRows = "1fr";
    } else {
      area.style.gridTemplateColumns = "1fr 1fr";
      area.style.gridTemplateRows = "1fr 1fr";
    }

    if (n === 3) {
      const last = this.panes.get(group.paneOrder[2]);
      if (last) {
        last.container.style.gridColumn = "1 / span 2";
        last.container.style.gridRow = "2";
      }
    }

    for (const sid of group.paneOrder) {
      const pane = this.panes.get(sid);
      if (!pane) continue;
      pane.fitAddon.fit();
      window.pywebview.api.resize(sid, pane.term.cols, pane.term.rows);
    }
  },

  closePane(sessionId) {
    const pane = this.panes.get(sessionId);
    if (!pane) return;
    const group = this.groups.get(pane.groupId);

    window.pywebview.api.close_session(sessionId);
    pane.term.dispose();
    pane.container.remove();
    this.panes.delete(sessionId);

    if (group) {
      group.paneOrder = group.paneOrder.filter((id) => id !== sessionId);
      if (group.paneOrder.length === 0) {
        this.groups.delete(pane.groupId);
        if (this.activeGroupId === pane.groupId) {
          const next = this.groups.keys().next();
          this.activeGroupId = next.done ? null : next.value;
          if (this.activeGroupId) this.switchGroup(this.activeGroupId);
        }
      } else if (this.focusedPaneId === sessionId) {
        this.focusedPaneId = group.paneOrder[0];
      }
    }

    this.renderTabStrip();
    this.applyActiveLayout();

    if (this.panes.size === 0) {
      document.getElementById("empty-state").classList.remove("hidden");
    }
  },

  closeGroup(groupId) {
    const group = this.groups.get(groupId);
    if (!group) return;
    for (const sessionId of [...group.paneOrder]) {
      this.closePane(sessionId);
    }
  },

  reconnect(sessionId) {
    const pane = this.panes.get(sessionId);
    if (!pane) return;
    // Wipe the old screen (and scrollback) before the new shell's first byte
    // arrives - otherwise a full-screen app's last frame (htop, uwsgitop)
    // can sit there looking live under/above the new prompt.
    pane.term.reset();
    window.pywebview.api.reconnect_session(sessionId, pane.term.cols, pane.term.rows);
  },

  async copyFromPane(sessionId) {
    const pane = this.panes.get(sessionId);
    if (!pane) return;
    const selection = pane.term.getSelection();
    if (!selection) return;
    await window.pywebview.api.set_clipboard(selection);
  },

  async pasteIntoPane(sessionId) {
    const pane = this.panes.get(sessionId);
    if (!pane) return;
    const text = await window.pywebview.api.get_clipboard();
    if (!text) return;
    window.pywebview.api.send_input(sessionId, text);
    pane.term.focus();
  },

  write(sessionId, text) {
    const pane = this.panes.get(sessionId);
    if (pane) pane.term.write(text);
  },

  setStatus(sessionId, state, message) {
    const pane = this.panes.get(sessionId);
    if (!pane) return;
    pane.state = state;
    pane.statusText.textContent = message || STATUS_LABEL[state] || state;
    pane.reconnectBtn.style.display = state === "disconnected" ? "" : "none";
    this.renderTabStrip();
  },
};

window.termWrite = (sessionId, text) => tabsManager.write(sessionId, text);
window.onSessionStatus = (sessionId, state, message) => tabsManager.setStatus(sessionId, state, message);
window.refreshProfiles = () => tabsManager.refreshProfiles();

onAppReady(() => tabsManager.init());
