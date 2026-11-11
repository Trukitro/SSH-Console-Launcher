const commandsPanel = {
  commands: [],

  init() {
    document.getElementById("new-command-btn").addEventListener("click", () => this.openForm());
    document.getElementById("command-close").addEventListener("click", () => this.closeForm());
    document.getElementById("c-save").addEventListener("click", () => this.save());
    document.getElementById("command-reference-btn").addEventListener("click", () => this.openReference());
    document.getElementById("reference-close").addEventListener("click", () => this.closeReference());
    this.refresh();
  },

  async refresh() {
    this.commands = await window.pywebview.api.list_commands();
    this.render();
  },

  byCategory() {
    const grouped = {};
    for (const cmd of this.commands) {
      (grouped[cmd.category] ||= []).push(cmd);
    }
    return grouped;
  },

  render() {
    const list = document.getElementById("command-list");
    list.innerHTML = "";

    for (const [category, cmds] of Object.entries(this.byCategory())) {
      const heading = document.createElement("div");
      heading.className = "command-category";
      heading.textContent = category;
      list.appendChild(heading);

      const wrap = document.createElement("div");
      wrap.className = "command-chips";
      for (const cmd of cmds) {
        const chip = document.createElement("div");
        chip.className = cmd.interactive ? "command-chip interactive" : "command-chip";
        const title = cmd.description ? `${cmd.command}\n${cmd.description}` : cmd.command;
        chip.title = cmd.interactive ? `${title}\n(full-screen / interactive)` : title;

        const label = document.createElement("span");
        label.textContent = cmd.interactive ? `⛶ ${cmd.name}` : cmd.name;

        const del = document.createElement("button");
        del.textContent = "×";
        del.addEventListener("click", async (e) => {
          e.stopPropagation();
          await window.pywebview.api.delete_command(cmd.id);
          this.refresh();
        });

        chip.appendChild(label);
        chip.appendChild(del);
        chip.addEventListener("click", () => this.run(cmd));
        wrap.appendChild(chip);
      }
      list.appendChild(wrap);
    }
  },

  run(cmd) {
    const sessionId = tabsManager.focusedPaneId;
    if (!sessionId) {
      alert("Open a connection first.");
      return;
    }
    const pane = tabsManager.panes.get(sessionId);
    // Re-sync the PTY size right before launching the command instead of
    // relying on whatever resize last fired from a layout change - closes a
    // race where a full-screen app (htop, uwsgitop) could draw its first
    // frame against a stale size if a split/resize just happened.
    if (pane) {
      pane.fitAddon.fit();
      window.pywebview.api.resize(sessionId, pane.term.cols, pane.term.rows);
    }
    window.pywebview.api.send_input(sessionId, cmd.command + "\r");
    if (pane) pane.term.focus();
  },

  openForm() {
    document.getElementById("c-name").value = "";
    document.getElementById("c-command").value = "";
    document.getElementById("c-category").value = "";
    document.getElementById("c-description").value = "";
    document.getElementById("c-interactive").checked = false;
    document.getElementById("c-error").textContent = "";
    document.getElementById("command-overlay").classList.remove("hidden");
  },

  closeForm() {
    document.getElementById("command-overlay").classList.add("hidden");
  },

  async save() {
    const name = document.getElementById("c-name").value.trim();
    const command = document.getElementById("c-command").value.trim();
    const category = document.getElementById("c-category").value.trim() || "General";
    const description = document.getElementById("c-description").value.trim();
    const interactive = document.getElementById("c-interactive").checked;
    const errorEl = document.getElementById("c-error");

    if (!name || !command) {
      errorEl.textContent = "Name and command are required.";
      return;
    }

    const result = await window.pywebview.api.save_command({ name, command, category, description, interactive });
    if (!result.ok) {
      errorEl.textContent = result.error;
      return;
    }
    this.closeForm();
    this.refresh();
  },

  // --- reference / help panel: same command list, but shown as a readable
  // cheat sheet (command + explanation) instead of compact chips ---

  async openReference() {
    // this.commands may not be populated yet if this is called before the
    // initial refresh() from init() has resolved (e.g. the user clicks "?"
    // immediately after the app window appears) - refresh explicitly so the
    // panel is never shown empty.
    await this.refresh();
    this.renderReference();
    document.getElementById("reference-overlay").classList.remove("hidden");
  },

  closeReference() {
    document.getElementById("reference-overlay").classList.add("hidden");
  },

  renderReference() {
    const list = document.getElementById("reference-list");
    list.innerHTML = "";

    for (const [category, cmds] of Object.entries(this.byCategory())) {
      const heading = document.createElement("div");
      heading.className = "reference-category";
      heading.textContent = category;
      list.appendChild(heading);

      for (const cmd of cmds) {
        const row = document.createElement("div");
        row.className = "reference-row";

        const info = document.createElement("div");
        info.className = "reference-info";
        const code = document.createElement("code");
        code.textContent = cmd.command;
        const desc = document.createElement("p");
        desc.textContent = cmd.description || cmd.name;
        info.appendChild(code);
        info.appendChild(desc);
        if (cmd.interactive) {
          const badge = document.createElement("p");
          badge.className = "reference-interactive-note";
          badge.textContent = "⛶ Full-screen / interactive - stays open until you exit it (e.g. q).";
          info.appendChild(badge);
        }

        const runBtn = document.createElement("button");
        runBtn.className = "reference-run-btn";
        runBtn.textContent = "Run";
        runBtn.addEventListener("click", () => this.run(cmd));

        row.appendChild(info);
        row.appendChild(runBtn);
        list.appendChild(row);
      }
    }
  },
};

onAppReady(() => commandsPanel.init());
