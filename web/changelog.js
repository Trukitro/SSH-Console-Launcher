// "What's changed" panel: reads CHANGELOG.md (bundled with the app) and
// renders it with light structure (headers, bullets) - not a full markdown
// parser, the file's format is ours to keep simple.

function renderChangelog(markdown) {
  const container = document.createElement("div");
  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line.trim()) continue;

    if (line.startsWith("## ")) {
      const h = document.createElement("div");
      h.className = "changelog-version";
      h.textContent = line.slice(3);
      container.appendChild(h);
    } else if (line.startsWith("# ")) {
      const h = document.createElement("div");
      h.className = "changelog-title";
      h.textContent = line.slice(2);
      container.appendChild(h);
    } else if (line.trim().startsWith("- ")) {
      const item = document.createElement("div");
      item.className = "changelog-item";
      item.textContent = line.trim().slice(2);
      container.appendChild(item);
    } else {
      const p = document.createElement("div");
      p.className = "changelog-text";
      p.textContent = line.trim();
      container.appendChild(p);
    }
  }
  return container;
}

const changelogPanel = {
  visible: false,
  loaded: false,

  init() {
    document.getElementById("changelog-toggle-btn").addEventListener("click", () => this.toggle());
    document.getElementById("changelog-close-btn").addEventListener("click", () => this.hide());
  },

  toggle() {
    if (this.visible) this.hide();
    else this.show();
  },

  async show() {
    this.visible = true;
    document.getElementById("changelog-overlay").classList.remove("hidden");
    if (!this.loaded) {
      const markdown = await window.pywebview.api.get_changelog();
      const body = document.getElementById("changelog-body");
      body.innerHTML = "";
      body.appendChild(renderChangelog(markdown));
      this.loaded = true;
    }
  },

  hide() {
    this.visible = false;
    document.getElementById("changelog-overlay").classList.add("hidden");
  },
};

onAppReady(() => changelogPanel.init());
