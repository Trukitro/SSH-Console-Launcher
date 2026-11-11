const transferPanel = {
  profile: null,

  init() {
    document.getElementById("transfer-close").addEventListener("click", () => this.close());
    document.getElementById("t-upload-btn").addEventListener("click", () => this.upload());
    document.getElementById("t-download-btn").addEventListener("click", () => this.download());
  },

  open(profile) {
    this.profile = profile;
    document.getElementById("transfer-title").textContent = `File transfer - ${profile.name}`;
    document.getElementById("t-remote-path").value = "";
    document.getElementById("t-error").textContent = "";
    document.getElementById("t-status").textContent = "";
    document.getElementById("transfer-overlay").classList.remove("hidden");
  },

  close() {
    document.getElementById("transfer-overlay").classList.add("hidden");
  },

  setStatus(text, isError) {
    document.getElementById(isError ? "t-error" : "t-status").textContent = text;
    document.getElementById(isError ? "t-status" : "t-error").textContent = "";
  },

  async upload() {
    const remotePath = document.getElementById("t-remote-path").value.trim();
    if (!remotePath) {
      this.setStatus("Enter the destination remote path first.", true);
      return;
    }
    const localPath = await window.pywebview.api.pick_upload_file();
    if (!localPath) return;

    this.setStatus("Uploading...", false);
    const result = await window.pywebview.api.upload_file(this.profile.id, localPath, remotePath);
    this.setStatus(result.ok ? "Upload complete." : result.error, !result.ok);
  },

  async download() {
    const remotePath = document.getElementById("t-remote-path").value.trim();
    if (!remotePath) {
      this.setStatus("Enter the remote path to download first.", true);
      return;
    }
    const suggestedName = remotePath.split("/").pop() || "download";
    const localPath = await window.pywebview.api.pick_download_target(suggestedName);
    if (!localPath) return;

    this.setStatus("Downloading...", false);
    const result = await window.pywebview.api.download_file(this.profile.id, remotePath, localPath);
    this.setStatus(result.ok ? "Download complete." : result.error, !result.ok);
  },
};

onAppReady(() => transferPanel.init());
