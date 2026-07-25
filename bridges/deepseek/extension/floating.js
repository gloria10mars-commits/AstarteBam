// NEMAPI Bridge — panneau flottant v2.7 (UI recovery + recv stable)

let mainTabId = null;

document.addEventListener("DOMContentLoaded", async () => {
  setupButtons();
  const status = await browser.runtime.sendMessage({ action: "getStatus" });
  if (status) {
    updateUI(!!status.connected || !!status.polling);
    if (status.targetTabId) {
      mainTabId = status.targetTabId;
      updateTabInfo();
    }
  }
  setInterval(async () => {
    try {
      const s = await browser.runtime.sendMessage({ action: "getStatus" });
      if (s) {
        updateUI(!!s.connected || !!s.polling);
        document.getElementById("btn-connect").textContent =
          s.connected || s.polling ? "Déconnecter" : "Connecter au proxy";
        if (s.targetTabId) {
          mainTabId = s.targetTabId;
          updateTabInfo();
        }
      }
    } catch (e) {}
  }, 2500);
});

function log(msg) {
  console.log("[FLOATING]", msg);
  const el = document.getElementById("log");
  if (el) el.textContent = msg;
}

function updateUI(connected) {
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (!dot || !label) return;
  if (connected) {
    dot.className = "status-dot status-on";
    label.textContent = "Connecté · v2.7 recovery + recv";
  } else {
    dot.className = "status-dot status-off";
    label.textContent = "Déconnecté";
  }
}

async function updateTabInfo() {
  const info = document.getElementById("target-tab-info");
  if (!info) return;
  if (!mainTabId) {
    info.textContent = "Non défini — capturer DeepSeek";
    return;
  }
  try {
    const tab = await browser.tabs.get(mainTabId);
    info.textContent = (tab.url || "").slice(0, 52) || "Tab #" + mainTabId;
  } catch (e) {
    info.textContent = "Tab #" + mainTabId;
  }
}

function setupButtons() {
  document.getElementById("btn-close").onclick = () => window.close();
  document.getElementById("btn-minimize").onclick = async () => {
    try {
      const win = await browser.windows.getCurrent();
      await browser.windows.update(win.id, { state: "minimized" });
    } catch (e) {}
  };

  document.getElementById("btn-connect").onclick = async () => {
    const status = await browser.runtime.sendMessage({ action: "getStatus" });
    if (status && (status.connected || status.polling)) {
      await browser.runtime.sendMessage({ action: "stopPolling" });
      updateUI(false);
      document.getElementById("btn-connect").textContent = "Connecter au proxy";
      log("Polling arrêté");
    } else {
      document.getElementById("btn-connect").textContent = "Connexion…";
      await browser.runtime.sendMessage({ action: "startPolling" });
      updateUI(true);
      document.getElementById("btn-connect").textContent = "Déconnecter";
      log("Polling proxy actif");
    }
  };

  document.getElementById("btn-capture").onclick = async () => {
    const resp = await browser.runtime.sendMessage({ action: "captureTab" });
    if (resp && resp.ok) {
      mainTabId = resp.tabId;
      updateTabInfo();
      log("Capturé: " + (resp.title || resp.url || resp.tabId));
    } else {
      log("Échec: " + ((resp && resp.error) || "?"));
    }
  };

  document.getElementById("btn-reset-session").onclick = async () => {
    const r = await browser.runtime.sendMessage({ action: "resetSession" });
    log(
      r && r.ok
        ? "Session proxy OK — ouvrez aussi un Nouveau chat DeepSeek"
        : "Reset échec"
    );
  };

  document.getElementById("btn-probe").onclick = async () => {
    const r = await browser.runtime.sendMessage({ action: "probeDom" });
    if (r && r.ok) {
      const p = r.probe || {};
      log(
        "DOM v" +
          (p.version || "?") +
          " input=" +
          !!p.input +
          " send=" +
          !!p.send +
          " asstLen=" +
          (p.lastAsstLen || 0) +
          " msgs=" +
          (p.dsMessageCount || 0)
      );
    } else {
      log("Probe: " + ((r && r.error) || "échec"));
    }
  };
}
