// Event Log panel: a structured, day-partitioned history of what the app
// has done (connections opened/closed, profiles created, the app starting
// up, errors) - not a raw technical log dump. Each entry is rendered as a
// bubble; today's log auto-refreshes while the panel is open, past days
// are loaded once and left static.

const KIND_LABELS = {
  system: "System",
  connection_open: "Connection",
  connection_reconnect: "Reconnect",
  connection_close: "Disconnected",
  connection_created: "Profile created",
  connection_updated: "Profile updated",
  log: "Log",
};

function formatEventKind(kind) {
  return KIND_LABELS[kind] || kind;
}

function formatEventDetail(detail) {
  if (!detail || Object.keys(detail).length === 0) return "";
  return Object.entries(detail)
    .map(([k, v]) => `${k}: ${v}`)
    .join("  ·  ");
}

function formatDateLabel(dateStr) {
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toISOString().slice(0, 10);
  if (dateStr === todayStr) return `Today (${dateStr})`;
  if (dateStr === yesterdayStr) return `Yesterday (${dateStr})`;
  return dateStr;
}

const debugConsole = {
  visible: false,
  pollTimer: null,
  currentDate: new Date().toISOString().slice(0, 10),
  levelFilter: "all",
  lastCount: -1,

  init() {
    document.getElementById("debug-toggle-btn").addEventListener("click", () => this.toggle());
    document.getElementById("debug-close-btn").addEventListener("click", () => this.hide());
    document.getElementById("debug-date-select").addEventListener("change", (e) => {
      this.currentDate = e.target.value;
      this.lastCount = -1;
      this.refresh();
    });
    document.getElementById("debug-level-select").addEventListener("change", (e) => {
      this.levelFilter = e.target.value;
      this.lastCount = -1;
      this.refresh();
    });
    this.initResize();
  },

  initResize() {
    const handle = document.getElementById("debug-console-resize-handle");
    const panel = document.getElementById("debug-console");
    let startY = 0;
    let startHeight = 0;

    const onMove = (e) => {
      const delta = startY - e.clientY;
      const newHeight = Math.min(Math.max(startHeight + delta, 160), Math.round(window.innerHeight * 0.8));
      panel.style.height = `${newHeight}px`;
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    handle.addEventListener("mousedown", (e) => {
      startY = e.clientY;
      startHeight = panel.getBoundingClientRect().height;
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      e.preventDefault();
    });
  },

  toggle() {
    if (this.visible) this.hide();
    else this.show();
  },

  async show() {
    this.visible = true;
    document.getElementById("debug-console").classList.remove("hidden");
    await this.loadDates();
    this.lastCount = -1;
    await this.refresh();
    // Only poll while the panel is actually open, and only today's log
    // actually changes - no reason to hit the bridge for a static past day.
    this.pollTimer = setInterval(() => this.refresh(), 1500);
    window.pywebview.api.log_event("system", "Opened debugger");
  },

  hide() {
    this.visible = false;
    document.getElementById("debug-console").classList.add("hidden");
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  async loadDates() {
    const dates = await window.pywebview.api.list_event_dates();
    const select = document.getElementById("debug-date-select");
    const previousValue = select.value || this.currentDate;
    select.innerHTML = "";
    for (const date of dates) {
      const option = document.createElement("option");
      option.value = date;
      option.textContent = formatDateLabel(date);
      select.appendChild(option);
    }
    select.value = dates.includes(previousValue) ? previousValue : dates[0];
    this.currentDate = select.value;
  },

  async refresh() {
    const todayStr = new Date().toISOString().slice(0, 10);
    let events = await window.pywebview.api.list_events(this.currentDate);
    if (this.levelFilter !== "all") {
      events = events.filter((e) => e.level === this.levelFilter);
    }
    if (events.length === this.lastCount) return; // nothing new, skip the re-render
    this.lastCount = events.length;

    const body = document.getElementById("debug-console-body");
    const wasScrolledToBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 20;

    body.innerHTML = "";
    if (events.length === 0) {
      const empty = document.createElement("div");
      empty.className = "event-empty";
      empty.textContent = this.currentDate === todayStr ? "Nothing logged yet today." : "No events on this day.";
      body.appendChild(empty);
    }
    for (const entry of events) {
      body.appendChild(this.renderBubble(entry));
    }

    if (wasScrolledToBottom) body.scrollTop = body.scrollHeight;
  },

  renderBubble(entry) {
    const bubble = document.createElement("div");
    bubble.className = `event-bubble level-${entry.level}`;

    const header = document.createElement("div");
    header.className = "event-bubble-header";
    const kind = document.createElement("span");
    kind.className = "event-kind";
    kind.textContent = formatEventKind(entry.kind);
    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = entry.time;
    header.appendChild(kind);
    header.appendChild(time);
    bubble.appendChild(header);

    const message = document.createElement("div");
    message.className = "event-message";
    message.textContent = entry.message;
    bubble.appendChild(message);

    const detailText = formatEventDetail(entry.detail);
    if (detailText) {
      const detail = document.createElement("div");
      detail.className = "event-detail";
      detail.textContent = detailText;
      bubble.appendChild(detail);
    }

    return bubble;
  },
};

onAppReady(() => debugConsole.init());
