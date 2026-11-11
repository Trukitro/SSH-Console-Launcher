const wizard = {
  overlay: null,
  state: {},

  init() {
    this.overlay = document.getElementById("wizard-overlay");

    document.getElementById("new-connection-btn").addEventListener("click", () => this.open());
    document.getElementById("wizard-close").addEventListener("click", () => this.close());

    document.getElementById("w-basics-next").addEventListener("click", () => this.submitBasics());
    document.getElementById("w-choose-key").addEventListener("click", () => this.chooseAuth("key"));
    document.getElementById("w-choose-password").addEventListener("click", () => this.chooseAuth("password"));
    document.getElementById("w-auth-back").addEventListener("click", () => this.showStep("basics"));

    document.getElementById("w-key-back").addEventListener("click", () => this.showStep("auth"));
    document.getElementById("w-key-install-btn").addEventListener("click", () => this.installKey());

    document.getElementById("w-password-back").addEventListener("click", () => this.showStep("auth"));
    document.getElementById("w-password-save").addEventListener("click", () => this.savePassword());
  },

  open(editProfile) {
    this.state = editProfile ? { ...editProfile } : {};
    document.getElementById("w-basics-title").textContent = editProfile ? `Edit ${editProfile.name}` : "New connection";
    document.getElementById("w-name").value = this.state.name || "";
    document.getElementById("w-host").value = this.state.host || "";
    document.getElementById("w-port").value = this.state.port || "22";
    document.getElementById("w-user").value = this.state.user || "";
    document.getElementById("w-key-install").classList.add("hidden");
    this.populateJumpHosts();
    this.clearErrors();
    this.showStep("basics");
    this.overlay.classList.remove("hidden");
  },

  populateJumpHosts() {
    const select = document.getElementById("w-jump");
    select.innerHTML = '<option value="">None - connect directly</option>';
    for (const profile of tabsManager.profiles) {
      if (profile.id === this.state.id) continue; // can't jump through itself
      const opt = document.createElement("option");
      opt.value = profile.id;
      opt.textContent = profile.name;
      select.appendChild(opt);
    }
    select.value = this.state.jump_profile_id || "";
  },

  close() {
    this.overlay.classList.add("hidden");
  },

  clearErrors() {
    document.querySelectorAll("#wizard-card .error").forEach((el) => (el.textContent = ""));
  },

  showStep(name) {
    document.querySelectorAll(".wizard-step").forEach((el) => {
      el.classList.toggle("hidden", el.dataset.step !== name);
    });
  },

  submitBasics() {
    const name = document.getElementById("w-name").value.trim();
    const host = document.getElementById("w-host").value.trim();
    const port = document.getElementById("w-port").value.trim() || "22";
    const user = document.getElementById("w-user").value.trim();
    const jump_profile_id = document.getElementById("w-jump").value;
    const errorEl = document.getElementById("w-basics-error");

    if (!name || !host || !user) {
      errorEl.textContent = "Name, host and user are required.";
      return;
    }
    errorEl.textContent = "";

    this.state = { ...this.state, name, host, port, user, jump_profile_id };
    this.showStep("auth");
  },

  chooseAuth(method) {
    this.state.auth_method = method;
    if (method === "key") {
      this.startKeyFlow();
    } else {
      this.showStep("password");
    }
  },

  async startKeyFlow() {
    this.showStep("key");
    document.getElementById("w-key-status").textContent = "Saving connection...";
    document.getElementById("w-key-install").classList.add("hidden");
    document.getElementById("w-key-error").textContent = "";

    const saveResult = await window.pywebview.api.save_profile({
      id: this.state.id,
      name: this.state.name,
      host: this.state.host,
      port: this.state.port,
      user: this.state.user,
      auth_method: "key",
      jump_profile_id: this.state.jump_profile_id || "",
    });
    if (!saveResult.ok) {
      document.getElementById("w-key-error").textContent = saveResult.error;
      return;
    }
    this.state.id = saveResult.id;

    document.getElementById("w-key-status").textContent = "Generating key pair...";
    const keyResult = await window.pywebview.api.generate_key(this.state.id);
    if (!keyResult.ok) {
      document.getElementById("w-key-error").textContent = keyResult.error;
      return;
    }
    this.state.key_path = keyResult.key_path;
    this.state.public_key = keyResult.public_key;

    document.getElementById("w-key-status").innerHTML =
      "Key pair generated. Enter the password once to install it on the server:" +
      `<pre class="pubkey">${keyResult.public_key}</pre>`;
    document.getElementById("w-key-install").classList.remove("hidden");
  },

  async installKey() {
    const password = document.getElementById("w-key-password").value;
    const errorEl = document.getElementById("w-key-error");
    const btn = document.getElementById("w-key-install-btn");
    if (!password) {
      errorEl.textContent = "Password is required to install the key.";
      return;
    }
    btn.disabled = true;
    btn.textContent = "Installing...";

    const result = await window.pywebview.api.install_key(
      this.state.host, this.state.port, this.state.user, password, this.state.public_key,
    );
    btn.disabled = false;
    btn.textContent = "Install key & save";

    if (!result.ok) {
      errorEl.textContent = result.error;
      return;
    }

    await window.pywebview.api.save_profile({
      id: this.state.id,
      name: this.state.name,
      host: this.state.host,
      port: this.state.port,
      user: this.state.user,
      auth_method: "key",
      key_path: this.state.key_path,
      jump_profile_id: this.state.jump_profile_id || "",
    });

    this.close();
    window.refreshProfiles();
  },

  async savePassword() {
    const password = document.getElementById("w-password").value;
    const errorEl = document.getElementById("w-password-error");
    if (!password) {
      errorEl.textContent = "Password is required.";
      return;
    }

    const result = await window.pywebview.api.save_profile({
      id: this.state.id,
      name: this.state.name,
      host: this.state.host,
      port: this.state.port,
      user: this.state.user,
      auth_method: "password",
      password,
      jump_profile_id: this.state.jump_profile_id || "",
    });
    if (!result.ok) {
      errorEl.textContent = result.error;
      return;
    }

    this.close();
    window.refreshProfiles();
  },
};

onAppReady(() => wizard.init());
