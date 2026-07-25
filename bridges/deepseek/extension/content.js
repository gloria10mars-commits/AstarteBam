// NEMAPI Bridge — Content script v2.7
// DeepSeek : SEND via barre de texte + récupération de la réponse.
// Réception multi-tour STABLE + auto-récupération si l'utilisateur a cliqué
// dans l'UI (menus, modales, faux loading, focus perdu).
// CRITICAL: ne JAMAIS cliquer regenerate/retry (faux positif près du composer).
// Pas de xdotool.

if (window.__NEMAPI_CONTENT_LOADED_V2_7__) {
  /* already loaded */
} else {
window.__NEMAPI_CONTENT_LOADED_V2_7__ = true;
window.__NEMAPI_CONTENT_LOADED_V2_6__ = true;
window.__NEMAPI_CONTENT_LOADED_V2_5__ = true;
window.__NEMAPI_CONTENT_LOADED_V2_4__ = true;
window.__NEMAPI_CONTENT_LOADED_V2_3__ = true;
window.__NEMAPI_CONTENT_LOADED_V2_2__ = true;
window.__NEMAPI_CONTENT_LOADED_V2__ = true;
window.__NEMAPI_CONTENT_LOADED__ = true;

let STOP_FLAG = false;
let JOB_BUSY = false;
let JOB_BUSY_SINCE = 0;
let JOB_WATCHDOG = null;
const JOB_MAX_MS = 15 * 60 * 1000; // filet de sécu si job coincé

function log(type, msg) {
  console.log("[NEMAPI] " + msg);
  try {
    browser.runtime.sendMessage({ from: "logger", type, msg });
  } catch (e) {}
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ═══════════════════════════════════════════
// Helpers DOM
// ═══════════════════════════════════════════

function isVisible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return false;
  const st = window.getComputedStyle(el);
  if (st.display === "none" || st.visibility === "hidden") return false;
  if (parseFloat(st.opacity || "1") < 0.05) return false;
  return true;
}

function isInViewport(el) {
  const r = el.getBoundingClientRect();
  return r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
}

function textOf(el) {
  if (!el) return "";
  return (el.innerText || el.textContent || "").trim();
}

function labelOf(el) {
  if (!el) return "";
  return (
    (el.getAttribute("aria-label") || "") +
    " " +
    (el.getAttribute("title") || "") +
    " " +
    (el.getAttribute("data-tooltip") || "") +
    " " +
    (el.getAttribute("alt") || "") +
    " " +
    (typeof el.className === "string" ? el.className : "") +
    " " +
    textOf(el)
  ).toLowerCase();
}

function docOrder(a, b) {
  const pos = a.compareDocumentPosition(b);
  if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
  if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
  return 0;
}

function clickEl(el) {
  if (!el) return false;
  try {
    el.scrollIntoView({ block: "center", behavior: "instant" });
  } catch (e) {}
  try {
    el.focus();
  } catch (e) {}
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  const opts = {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX: x,
    clientY: y,
    buttons: 1,
  };
  try {
    el.dispatchEvent(new PointerEvent("pointerdown", opts));
  } catch (e) {}
  try {
    el.dispatchEvent(new MouseEvent("mousedown", opts));
  } catch (e) {}
  try {
    el.dispatchEvent(new PointerEvent("pointerup", opts));
  } catch (e) {}
  try {
    el.dispatchEvent(new MouseEvent("mouseup", opts));
  } catch (e) {}
  try {
    el.dispatchEvent(new MouseEvent("click", opts));
  } catch (e) {}
  try {
    if (typeof el.click === "function") el.click();
  } catch (e) {}
  return true;
}

function setNativeValue(el, text) {
  if (!el) return false;
  el.focus();
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
    const proto =
      el.tagName === "TEXTAREA"
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, text);
    else el.value = text;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    try {
      el.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          data: text,
          inputType: "insertFromPaste",
        })
      );
    } catch (e) {}
    return true;
  }
  if (el.isContentEditable || el.getAttribute("contenteditable") === "true") {
    el.focus();
    try {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
    } catch (e) {
      el.textContent = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }
  return false;
}

function b64ToUint8Array(b64) {
  const clean = String(b64 || "").replace(/\s/g, "");
  const bin = atob(clean);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

// ═══════════════════════════════════════════
// Composer (bas de page)
// ═══════════════════════════════════════════

function findMainComposer() {
  const selectors = [
    "textarea#chat-input",
    "textarea[placeholder]",
    "div[contenteditable='true'][role='textbox']",
    "textarea",
  ];
  let best = null;
  let bestScore = -1;
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      if (!isVisible(el)) continue;
      if (el.closest(".ds-virtual-list, [class*='ds-virtual-list'], [class*='virtual-list']")) {
        const r = el.getBoundingClientRect();
        if (r.bottom < window.innerHeight * 0.75) continue;
      }
      const r = el.getBoundingClientRect();
      let score = r.top + r.height * 0.5;
      if (r.bottom > window.innerHeight * 0.55) score += 1000;
      if (r.width > 200) score += 50;
      if (!el.closest(".ds-virtual-list, [class*='ds-virtual-list']")) score += 200;
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    }
  }
  return best;
}

/**
 * Boutons d'action sur un message (regen / copy / edit…) — JAMAIS le send.
 * C'était le bug multi-tour : le bouton « Regenerate » du dernier assistant
 * est souvent juste au-dessus du composer → findSendNear le prenait.
 */
function isMessageActionButton(btn) {
  if (!btn) return true;
  if (
    btn.closest(
      [
        ".ds-message",
        "[class*='ds-message']",
        "[class*='message-action']",
        "[class*='MessageAction']",
        "[class*='md-action']",
        "[class*='msg-action']",
        "[class*='toolbar']",
        "[class*='feedback']",
        "[class*='reaction']",
        "article",
        "[data-message-id]",
        "[class*='chat-message']",
        "[class*='assistant-message']",
        "[class*='ai-message']",
      ].join(", ")
    )
  ) {
    // Exception : si le bouton est aussi dans le composer bas, ce n'est pas une action message
    if (
      btn.closest(
        "form, [class*='composer'], [class*='input-area'], [class*='chat-input'], [class*='ChatInput'], footer"
      )
    ) {
      const r = btn.getBoundingClientRect();
      if (r.top > window.innerHeight * 0.72) return false;
    }
    return true;
  }
  const lab = labelOf(btn);
  if (
    /regenerat|re-generat|retry|réessay|reessay|ressay|again|réécrire|rewrite|edit\b|éditer|modifier|copy|copie|copied|like|dislike|thumb|share|partager|feedback|good response|bad response|signaler|report/i.test(
      lab
    )
  ) {
    return true;
  }
  return false;
}

function isInComposerChrome(btn, composer) {
  if (!btn) return false;
  if (
    btn.closest(
      "form, [class*='composer'], [class*='input-area'], [class*='chat-input'], [class*='ChatInput'], [class*='textarea'], [class*='editor-wrap']"
    )
  ) {
    return true;
  }
  if (composer) {
    // Même parent raisonnable (quelques niveaux) + zone basse
    let a = composer.parentElement;
    for (let i = 0; i < 6 && a; i++) {
      if (a.contains(btn) && a !== document.body && a !== document.documentElement) {
        const r = btn.getBoundingClientRect();
        if (r.top > window.innerHeight * 0.65) return true;
      }
      a = a.parentElement;
    }
  }
  return false;
}

function findSendNear(el) {
  // Mots du bouton d'envoi (pas regenerate)
  const keywords =
    /send|envoyer|submit|arrow|plane|paper|发送|送出|soumettre|go\b/i;
  const stopWords =
    /stop|arrêt|cancel|abort|regenerat|retry|réessay|edit|copy|copie|éditer|like|dislike|attach|upload|file|fichier|new chat|nouveau|settings|param|mic|voice|audio|search|web/i;

  const candidates = Array.from(
    document.querySelectorAll("button, [role='button'], [type='submit']")
  ).filter((btn) => {
    if (!isVisible(btn)) return false;
    if (isMessageActionButton(btn)) return false;
    const lab = labelOf(btn);
    if (stopWords.test(lab) && !keywords.test(lab)) return false;
    // Zone basse uniquement (composer)
    const r = btn.getBoundingClientRect();
    if (r.top < window.innerHeight * 0.55) return false;
    return true;
  });

  if (el) {
    const ir = el.getBoundingClientRect();
    let best = null;
    let bestScore = -Infinity;

    for (const btn of candidates) {
      const r = btn.getBoundingClientRect();
      // Aligné horizontalement avec le composer, à sa droite
      if (Math.abs(r.top + r.height / 2 - (ir.top + ir.height / 2)) > 80) continue;
      if (r.left + r.width / 2 < ir.left - 20) continue;

      const lab = labelOf(btn);
      let score = 0;
      if (keywords.test(lab)) score += 100;
      if (isInComposerChrome(btn, el)) score += 80;
      // Proximité à droite du champ
      const d = Math.hypot(
        Math.max(0, r.left - ir.right),
        r.top + r.height / 2 - (ir.top + ir.height / 2)
      );
      score += Math.max(0, 200 - d);
      // Préférer bas de page
      score += (r.top / window.innerHeight) * 30;
      // Boutons icône carrés près du composer (plane)
      if (r.width <= 64 && r.height <= 64 && r.left >= ir.right - 40) score += 40;

      if (score > bestScore) {
        bestScore = score;
        best = btn;
      }
    }
    if (best && bestScore >= 40) {
      log(
        "info",
        "Send btn score=" +
          Math.round(bestScore) +
          " lab=" +
          labelOf(best).slice(0, 60)
      );
      return best;
    }
  }

  // Fallback : mot-clé send uniquement en zone basse + pas action message
  for (const btn of candidates) {
    const lab = labelOf(btn);
    if (keywords.test(lab) && !stopWords.test(lab)) return btn;
  }
  return null;
}

function getComposerText(input) {
  if (!input) return "";
  if (input.value != null && typeof input.value === "string") return input.value;
  return textOf(input);
}

function pressEnterToSend(input) {
  if (!input) return;
  try {
    input.focus();
  } catch (e) {}
  const base = {
    key: "Enter",
    code: "Enter",
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true,
  };
  // DeepSeek écoute souvent keydown (sans Shift = send)
  try {
    input.dispatchEvent(
      new KeyboardEvent("keydown", { ...base, shiftKey: false, ctrlKey: false })
    );
  } catch (e) {}
  try {
    input.dispatchEvent(new KeyboardEvent("keypress", { ...base, shiftKey: false }));
  } catch (e) {}
  try {
    input.dispatchEvent(new KeyboardEvent("keyup", { ...base, shiftKey: false }));
  } catch (e) {}
  // Form submit si présent
  const form = input.closest("form");
  if (form) {
    try {
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    } catch (e) {}
  }
}

function findStopButton() {
  for (const btn of document.querySelectorAll("button, [role='button']")) {
    if (!isVisible(btn)) continue;
    // Stop de génération seulement (pas "stop" générique hors bas de page)
    const lab = labelOf(btn);
    if (!/stop|arrêt|arreter|stop generating|停止|中止/.test(lab)) continue;
    // Exclure navigation / audio
    if (/stop mic|stop record|stop video/i.test(lab)) continue;
    const r = btn.getBoundingClientRect();
    // Bouton stop DeepSeek est en bas (zone composer) ou sur le stream
    if (r.top < window.innerHeight * 0.35 && r.bottom < window.innerHeight * 0.5) {
      // trop haut : souvent pas le stop de chat
      if (!/stop generating|arrêt|停止|generating/i.test(lab)) continue;
    }
    return btn;
  }
  return null;
}

/**
 * Génération en cours — STRICT.
 * Après un clic manuel, DeepSeek laisse souvent des [class*=loading] / aria-busy
 * sur des skeletons ou spinners hors chat → l'ancien isGenerating restait true
 * et bloquait l'envoi/attente indéfiniment.
 */
function isGenerating() {
  // Signal fiable n°1 : bouton Stop
  if (findStopButton()) return true;

  // Signal n°2 : indicateurs de stream UNIQUEMENT dans la zone messages bas
  const candidates = document.querySelectorAll(
    "[class*='streaming'], [class*='generating'], [class*='ds-loading'], [data-streaming='true']"
  );
  for (const el of candidates) {
    if (!isVisible(el)) continue;
    if (isInComposerZone(el)) continue;
    const r = el.getBoundingClientRect();
    // bas de la conversation / message en cours
    if (r.top < window.innerHeight * 0.15) continue;
    if (r.bottom < window.innerHeight * 0.2) continue;
    const cn = (typeof el.className === "string" ? el.className : "") + " " + labelOf(el);
    if (/stream|generat|thinking|réfle|typing|cursor/i.test(cn)) return true;
  }

  // aria-busy uniquement sur un message bas (pas sur toute la page)
  for (const el of document.querySelectorAll("[aria-busy='true']")) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight * 0.25) continue;
    if (r.bottom > window.innerHeight * 0.95) continue;
    if (el.closest("textarea, [contenteditable='true'], nav, header, aside")) continue;
    if (looksLikeAssistantMessage(el) || el.closest(".ds-message, [class*='ds-message']")) {
      return true;
    }
  }
  return false;
}

function pressKeyOn(target, key, opts) {
  const el = target || document.activeElement || document.body;
  const base = {
    key,
    code: key === "Escape" ? "Escape" : key,
    keyCode: key === "Escape" ? 27 : key === "Enter" ? 13 : 0,
    which: key === "Escape" ? 27 : key === "Enter" ? 13 : 0,
    bubbles: true,
    cancelable: true,
    ...(opts || {}),
  };
  try {
    el.dispatchEvent(new KeyboardEvent("keydown", base));
  } catch (e) {}
  try {
    el.dispatchEvent(new KeyboardEvent("keyup", base));
  } catch (e) {}
  try {
    document.dispatchEvent(new KeyboardEvent("keydown", base));
  } catch (e) {}
}

/**
 * Ferme menus / popovers / modales / drawers ouverts par un clic utilisateur.
 * Sans ça le composer est masqué ou Enter n'envoie plus.
 */
async function dismissUiInterference() {
  let closed = 0;

  // 1) Escape ×3 (menus, tooltips, command palette)
  for (let i = 0; i < 3; i++) {
    pressKeyOn(document.activeElement || document.body, "Escape");
    await sleep(80);
  }

  // 2) Boutons close visibles sur dialogs
  const closeRe =
    /close|fermer|dismiss|cancel|annuler|got it|ok\b|×|✕|关闭|取消/i;
  const dialogs = document.querySelectorAll(
    "[role='dialog'], [aria-modal='true'], [class*='modal'], [class*='Modal'], [class*='dialog'], [class*='Dialog'], [class*='popover'], [class*='Popover'], [class*='dropdown'][class*='open'], [class*='menu'][class*='open'], [class*='Drawer'], [class*='drawer']"
  );
  for (const dlg of dialogs) {
    if (!isVisible(dlg)) continue;
    // Ne pas fermer le panneau de chat principal
    if (dlg.querySelector("textarea#chat-input, textarea[placeholder]")) continue;
    const r = dlg.getBoundingClientRect();
    if (r.width > window.innerWidth * 0.95 && r.height > window.innerHeight * 0.95) {
      // plein écran : chercher close
    }
    const btns = dlg.querySelectorAll("button, [role='button'], [aria-label]");
    for (const b of btns) {
      if (!isVisible(b)) continue;
      const lab = labelOf(b);
      if (closeRe.test(lab) || lab.trim() === "×" || lab.includes("close")) {
        try {
          b.click();
          closed++;
        } catch (e) {}
        await sleep(100);
        break;
      }
    }
  }

  // 3) Backdrop cliquable
  for (const bd of document.querySelectorAll(
    "[class*='overlay'], [class*='backdrop'], [class*='mask'], [class*='Modal-mask']"
  )) {
    if (!isVisible(bd)) continue;
    const r = bd.getBoundingClientRect();
    if (r.width < window.innerWidth * 0.3) continue;
    try {
      bd.click();
      closed++;
    } catch (e) {}
    await sleep(80);
  }

  // 4) Escape encore après closes
  pressKeyOn(document.body, "Escape");
  await sleep(100);

  if (closed) log("info", "UI interférence fermée (actions=" + closed + ")");
  return closed;
}

/**
 * Remet l'interface dans un état automatisable après clics manuels.
 */
async function prepareChatForAutomation(opts) {
  const options = opts || {};
  log("info", "Préparation UI (récupération post-clic)…");
  STOP_FLAG = false;

  await dismissUiInterference();
  scrollChatToBottom();
  await sleep(150);

  // Si une génération a été déclenchée par accident (regen, etc.)
  if (options.stopIfGenerating !== false && isGenerating()) {
    log("info", "Génération en cours détectée — attente courte puis stop si bloquant");
    const t0 = Date.now();
    while (isGenerating() && Date.now() - t0 < 4000) {
      await sleep(200);
    }
    if (isGenerating() && options.forceStop) {
      const stop = findStopButton();
      if (stop) {
        try {
          stop.click();
        } catch (e) {
          clickEl(stop);
        }
        log("info", "Stop forcé (UI destabilisée)");
        await sleep(600);
      }
    }
  }

  // Re-focus composer
  let input = findMainComposer();
  if (!input) {
    await dismissUiInterference();
    scrollChatToBottom();
    await sleep(200);
    input = findMainComposer();
  }
  if (input) {
    try {
      input.scrollIntoView({ block: "end", behavior: "instant" });
    } catch (e) {}
    try {
      input.focus();
    } catch (e) {}
    // clic doux dans le composer pour sortir d'un mode "sélection message"
    try {
      const r = input.getBoundingClientRect();
      input.dispatchEvent(
        new MouseEvent("mousedown", {
          bubbles: true,
          clientX: r.left + 20,
          clientY: r.top + 10,
        })
      );
      input.dispatchEvent(
        new MouseEvent("mouseup", {
          bubbles: true,
          clientX: r.left + 20,
          clientY: r.top + 10,
        })
      );
      input.click();
    } catch (e) {}
    await sleep(100);
  }

  const ok = !!findMainComposer() && !document.querySelector("[aria-modal='true'][style*='display: none']");
  // modal encore ouvert ?
  const blockingModal = Array.from(
    document.querySelectorAll("[role='dialog'], [aria-modal='true']")
  ).some((el) => {
    if (!isVisible(el)) return false;
    if (el.querySelector("textarea#chat-input, textarea[placeholder]")) return false;
    const r = el.getBoundingClientRect();
    return r.width > 80 && r.height > 80;
  });
  if (blockingModal) {
    await dismissUiInterference();
  }

  log(
    "info",
    "UI prête — composer=" +
      !!findMainComposer() +
      " generating=" +
      isGenerating() +
      " modal=" +
      blockingModal
  );
  return !!findMainComposer();
}

function clearJobWatchdog() {
  if (JOB_WATCHDOG) {
    clearTimeout(JOB_WATCHDOG);
    JOB_WATCHDOG = null;
  }
}

function armJobWatchdog(jobId) {
  clearJobWatchdog();
  JOB_BUSY_SINCE = Date.now();
  JOB_WATCHDOG = setTimeout(() => {
    if (JOB_BUSY) {
      log("error", "Watchdog: job coincé > " + JOB_MAX_MS + "ms — libération");
      JOB_BUSY = false;
      STOP_FLAG = true;
      try {
        browser.runtime.sendMessage({
          action: "automationError",
          jobId,
          error: "Watchdog: job coincé (timeout interne extension)",
        });
      } catch (e) {}
    }
  }, JOB_MAX_MS);
}

function forceUnlockJob(reason) {
  log("info", "forceUnlockJob: " + (reason || ""));
  STOP_FLAG = true;
  JOB_BUSY = false;
  JOB_BUSY_SINCE = 0;
  clearJobWatchdog();
  // laisser STOP propager puis reset pour le prochain job
  setTimeout(() => {
    STOP_FLAG = false;
  }, 500);
}

// ═══════════════════════════════════════════
// Messages — tours user/assistant (ordre DOM)
// ═══════════════════════════════════════════

function isInComposerZone(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  if (r.top > window.innerHeight * 0.9) return true;
  if (el.closest("form, [class*='composer'], [class*='input-area'], [class*='chat-input']")) {
    const cr = el.getBoundingClientRect();
    if (cr.bottom > window.innerHeight * 0.75) return true;
  }
  return false;
}

function looksLikeUserMessage(el) {
  if (!el) return false;
  const role = (el.getAttribute("data-role") || "").toLowerCase();
  if (role === "user" || role === "human") return true;
  if (role === "assistant" || role === "ai" || role === "bot") return false;
  const lab =
    labelOf(el) +
    " " +
    role +
    " " +
    (typeof el.className === "string" ? el.className : "");
  if (/user|human|question|prompt|author-user|role-user|\bself\b/i.test(lab) &&
      !/assistant|ai-message|bot-message|model-message/i.test(lab)) {
    return true;
  }
  if (/assistant|ai-message|bot|model|ds-markdown/i.test(lab)) return false;
  const cn = typeof el.className === "string" ? el.className : "";
  if (/\bds-message\b/.test(cn) || /ds-message/.test(cn)) {
    if (!el.querySelector("[class*='ds-markdown'], [class*='markdown'], pre, code")) {
      return true;
    }
  }
  const r = el.getBoundingClientRect();
  const mid = window.innerWidth / 2;
  // Bulles user DeepSeek souvent alignées à droite
  if (r.left > mid * 0.85 && r.width < window.innerWidth * 0.75 && r.width > 40) {
    return true;
  }
  return false;
}

function looksLikeAssistantMessage(el) {
  if (!el) return false;
  const role = (el.getAttribute("data-role") || "").toLowerCase();
  if (role === "assistant" || role === "ai" || role === "bot" || role === "model") return true;
  if (role === "user" || role === "human") return false;
  const lab = labelOf(el) + " " + (typeof el.className === "string" ? el.className : "");
  if (/assistant|ai-message|ds-markdown|bot|model/i.test(lab)) return true;
  if (
    el.querySelector(
      "pre, code, .markdown, [class*='markdown'], [class*='Markdown'], [class*='ds-markdown']"
    )
  ) {
    return true;
  }
  return false;
}

/** Force le virtual-list DeepSeek à monter les derniers messages. */
function scrollChatToBottom() {
  try {
    window.scrollTo(0, document.documentElement.scrollHeight);
  } catch (e) {}
  const selectors = [
    "[class*='ds-scroll']",
    "[class*='scroll-area']",
    "[class*='virtual-list']",
    "[class*='chat-list']",
    "[class*='message-list']",
    "main",
  ];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      try {
        if (el.scrollHeight > el.clientHeight + 20) {
          el.scrollTop = el.scrollHeight;
        }
      } catch (e) {}
    }
  }
  try {
    const composer = findMainComposer();
    if (composer) composer.scrollIntoView({ block: "end", behavior: "instant" });
  } catch (e) {}
}

function findMessageRoots() {
  const selectors = [
    ".ds-message",
    "[class*='ds-message']",
    ".ds-virtual-list-visible-items > div",
    "[class*='ds-virtual-list-visible'] > div",
    "[class*='_message']",
    "[data-message-id]",
    "[data-role='user']",
    "[data-role='assistant']",
  ];
  const found = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      if (isInComposerZone(el)) continue;
      if (el.closest("textarea, [contenteditable='true']")) continue;
      // Garder hors-viewport (virtual list recycle) si dans la zone chat
      const t = textOf(el);
      if (t.length < 1 || t.length > 500000) continue;
      const r = el.getBoundingClientRect();
      if (r.top > window.innerHeight * 0.94 && r.height < 8) continue;
      seen.add(el);
      found.push(el);
    }
  }
  const filtered = found.filter((el) => {
    return !found.some((other) => other !== el && other.contains(el));
  });
  filtered.sort(docOrder);
  return filtered;
}

/**
 * Blocs markdown assistant en ordre document (du plus ancien au plus récent).
 * Ne pas prendre le "plus long" — bug multi-tour (réponse courte ignorée).
 */
function collectAssistantBlocks() {
  const selectors = [
    "[class*='ds-markdown']",
    ".ds-message [class*='markdown']",
    "[data-role='assistant']",
    "[class*='assistant'] [class*='markdown']",
    "div.prose",
  ];
  const raw = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      if (seen.has(el)) continue;
      if (isInComposerZone(el)) continue;
      if (el.closest("textarea, [contenteditable='true']")) continue;
      const host = el.closest(".ds-message, [class*='ds-message'], [data-role]") || el;
      if (looksLikeUserMessage(host)) continue;
      const t = textOf(el);
      if (t.length < 1 || t.length > 500000) continue;
      seen.add(el);
      raw.push(el);
    }
  }

  const roots = raw.filter(
    (el) => !raw.some((other) => other !== el && other.contains(el))
  );
  roots.sort(docOrder);

  return roots.map((el) => {
    const t = textOf(el);
    return { el, text: t, len: t.length };
  });
}

function collectUserBlocks() {
  const roots = findMessageRoots();
  const users = [];
  for (const el of roots) {
    if (!looksLikeUserMessage(el)) continue;
    if (looksLikeAssistantMessage(el) && el.querySelector("[class*='ds-markdown']")) {
      continue;
    }
    const t = textOf(el);
    if (t.length < 1) continue;
    users.push({ el, text: t, len: t.length });
  }
  // Fallback : bulles sans markdown, alignées à droite
  if (!users.length) {
    for (const el of roots) {
      if (looksLikeAssistantMessage(el)) continue;
      const t = textOf(el);
      if (t.length < 2) continue;
      if (el.querySelector("[class*='ds-markdown'], pre, code")) continue;
      users.push({ el, text: t, len: t.length });
    }
  }
  return users;
}

/** Empreinte d'UN seul texte (pas tout le fil — le virtual-list change les anciens). */
function fingerprintText(s) {
  const n = normalizeForCompare(s);
  if (!n) return "0:";
  return n.length + ":" + n.slice(0, 64) + "|" + n.slice(-64);
}

function normalizeForCompare(s) {
  return String(s || "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Extrait un fragment identifiable du prompt envoyé (après [USER] si pack_delta).
 */
function extractUserNeedle(sentText) {
  let s = String(sentText || "").trim();
  if (!s) return "";
  // pack_delta : "[USER]\n...."
  const m = s.match(/\[USER\]\s*\n([\s\S]+)/i);
  if (m) s = m[1].trim();
  // Enlever préfixes system/tools en tête
  s = s.replace(/^\[SYSTEM\][\s\S]*?(?=\[USER\]|$)/i, "").trim();
  const n = normalizeForCompare(s);
  if (n.length <= 80) return n;
  // Needle : début + milieu pour coller même si l'UI tronque l'affichage
  return n.slice(0, 72);
}

function textIncludesNeedle(hay, needle) {
  const h = normalizeForCompare(hay);
  const n = normalizeForCompare(needle);
  if (!n || !h) return false;
  if (h.includes(n)) return true;
  if (n.length > 24 && h.includes(n.slice(0, 24))) return true;
  // Similarité grossière (fichiers + prompt long)
  if (n.length > 40 && h.length > 20) {
    const a = n.slice(0, 40);
    if (h.includes(a.slice(0, 20))) return true;
  }
  return false;
}

/**
 * Dernier assistant qui suit le dernier user dans le DOM (ordre document).
 * Si le virtual-list ne montre que des assistants, fallback last markdown.
 */
function findAssistantAfterLastUser() {
  const roots = findMessageRoots();
  let lastUserIdx = -1;
  for (let i = 0; i < roots.length; i++) {
    if (looksLikeUserMessage(roots[i]) && !looksLikeAssistantMessage(roots[i])) {
      lastUserIdx = i;
    } else if (looksLikeUserMessage(roots[i])) {
      // user pur
      lastUserIdx = i;
    }
  }
  // Re-scan : préférer data-role / alignement
  lastUserIdx = -1;
  for (let i = 0; i < roots.length; i++) {
    if (looksLikeUserMessage(roots[i])) lastUserIdx = i;
  }

  if (lastUserIdx >= 0) {
    for (let i = roots.length - 1; i > lastUserIdx; i--) {
      const el = roots[i];
      if (looksLikeUserMessage(el) && !el.querySelector("[class*='ds-markdown']")) continue;
      if (looksLikeAssistantMessage(el) || el.querySelector("[class*='ds-markdown'], pre, code")) {
        // Préférer le markdown interne
        const md = el.querySelector("[class*='ds-markdown'], [class*='markdown']");
        const t = textOf(md || el);
        if (t.length > 0) return t;
      }
    }
  }

  const blocks = collectAssistantBlocks();
  if (blocks.length) return blocks[blocks.length - 1].text;

  for (let i = roots.length - 1; i >= 0; i--) {
    if (looksLikeAssistantMessage(roots[i]) && !looksLikeUserMessage(roots[i])) {
      const t = textOf(roots[i]);
      if (t.length > 0) return t;
    }
  }
  return "";
}

/** Dernier texte assistant visible (ordre DOM). */
function findLastAssistantText() {
  return findAssistantAfterLastUser();
}

/**
 * État de tour complet pour la réception.
 * lastFp = empreinte du DERNIER assistant uniquement (pas de sig global fragile).
 */
function snapshotThread() {
  scrollChatToBottom();
  const asstBlocks = collectAssistantBlocks();
  const userBlocks = collectUserBlocks();
  const lastAsst = findAssistantAfterLastUser();
  const lastUser = userBlocks.length ? userBlocks[userBlocks.length - 1].text : "";
  // sig global seulement pour debug — ne JAMAIS décider seul d'un succès
  const sig = asstBlocks
    .map((b) => fingerprintText(b.text))
    .join("§");
  return {
    count: asstBlocks.length,
    userCount: userBlocks.length,
    last: lastAsst,
    lastLen: (lastAsst || "").length,
    lastUser,
    lastUserLen: (lastUser || "").length,
    lastFp: fingerprintText(lastAsst),
    lastUserFp: fingerprintText(lastUser),
    sig,
    ts: Date.now(),
  };
}

/**
 * Une réponse est valide SEULEMENT si :
 *  - le texte du dernier assistant a changé par rapport à la baseline, OU
 *  - le nombre d'assistants a augmenté après confirmation du tour user
 * Ne jamais accepter un simple changement de sig (virtual-list remount).
 */
function isGenuineNewAssistant(snap, baseline) {
  const cur = normalizeForCompare(snap.last || "");
  const baseLast = normalizeForCompare(baseline.last || "");
  if (!cur) return false;
  if (cur !== baseLast) return true;
  // Même texte (réponse identique rare) : seulement si +1 assistant ET user a bougé
  if (
    snap.count > (baseline.count || 0) &&
    (snap.userCount > (baseline.userCount || 0) ||
      fingerprintText(snap.lastUser) !== fingerprintText(baseline.lastUser || ""))
  ) {
    return true;
  }
  return false;
}

function userTurnConfirmed(snap, baseline, sentNeedle) {
  // 1) Nouveau message user détecté
  if (snap.userCount > (baseline.userCount || 0)) return true;
  // 2) Dernier user a changé
  if (
    snap.lastUser &&
    fingerprintText(snap.lastUser) !== fingerprintText(baseline.lastUser || "")
  ) {
    return true;
  }
  // 3) Needle du prompt visible dans le dernier user
  if (sentNeedle && snap.lastUser && textIncludesNeedle(snap.lastUser, sentNeedle)) {
    // S'assurer que ce n'était pas déjà le cas avant envoi
    if (!textIncludesNeedle(baseline.lastUser || "", sentNeedle)) return true;
  }
  // 4) Composer vidé + génération = envoi OK (fallback si virtual-list cache le user)
  return false;
}

/**
 * Attente multi-tour robuste (v2.6) :
 * Phase 0 — scroll bas
 * Phase 1 — confirmer tour USER (ou génération démarrée après envoi)
 * Phase 2 — attendre assistant NOUVEAU (texte ≠ baseline), stable, génération finie
 * INTERDIT : accepter l'ancienne réponse parce que le sig du fil a bougé
 */
async function waitForAssistantResponse(baseline, timeoutMs, sentText) {
  const t0 = Date.now();
  let lastStable = "";
  let stableCount = 0;
  let sawGenerating = false;
  let sawGenuineChange = false;
  let sawUserTurn = false;
  let maxSeenLen = 0;
  let growthTicks = 0;
  let prevLen = 0;
  const baseLast = normalizeForCompare(baseline.last || "");
  const baseCount = baseline.count || 0;
  const sentNeedle = extractUserNeedle(sentText || "");

  log(
    "info",
    "Wait v2.6 — baseAsst=" +
      baseCount +
      " baseLen=" +
      (baseline.lastLen || 0) +
      " baseUser=" +
      (baseline.userCount || 0) +
      " needle=" +
      (sentNeedle ? sentNeedle.slice(0, 40) : "∅")
  );

  // Petit délai pour laisser le user message apparaître
  scrollChatToBottom();

  while (Date.now() - t0 < timeoutMs) {
    if (STOP_FLAG) throw new Error("stopped");

    // Rescroll périodique (virtual list)
    if ((Date.now() - t0) % 2000 < 500) scrollChatToBottom();

    const generating = isGenerating();
    if (generating) sawGenerating = true;

    const snap = snapshotThread();
    if (!sawUserTurn) {
      sawUserTurn = userTurnConfirmed(snap, baseline, sentNeedle);
      if (sawUserTurn) {
        log("info", "Tour USER confirmé (users=" + snap.userCount + ")");
      }
    }

    // Génération après envoi = preuve forte même sans bulle user visible
    const genImpliesSend =
      sawGenerating ||
      (getComposerText(findMainComposer()).trim().length === 0 && generating);

    const genuine = isGenuineNewAssistant(snap, baseline);
    const cur = normalizeForCompare(snap.last || "");
    const curRaw = snap.last || "";

    // Garde-fou : jamais traiter l'ancien texte comme "changement"
    if (genuine && cur) {
      // Exiger soit un vrai changement de contenu, soit count++ après user/gen
      const contentDiffers = cur !== baseLast;
      const countGrew = snap.count > baseCount;
      // Si on n'a ni user turn ni gen et seul count flotte (virtual list) → ignorer
      if (!contentDiffers && !sawUserTurn && !sawGenerating) {
        await sleep(350);
        continue;
      }
      // Si contentDiffers mais on n'a jamais vu gen ni user et c'est tout de suite
      // (<800ms) : possible glitch DOM — attendre un peu sauf count++
      const elapsed = Date.now() - t0;
      if (contentDiffers && !sawGenerating && !sawUserTurn && !countGrew && elapsed < 900) {
        await sleep(350);
        continue;
      }

      sawGenuineChange = true;
      if (cur.length > maxSeenLen) maxSeenLen = cur.length;
      if (cur.length > prevLen) growthTicks++;
      prevLen = cur.length;

      if (cur === lastStable) stableCount++;
      else {
        lastStable = cur;
        stableCount = 0;
      }

      // Conditions de succès strictes
      const readyToAccept =
        contentDiffers ||
        (countGrew && (sawUserTurn || sawGenerating));

      if (readyToAccept && !generating) {
        // Stable ~1.4–2s selon longueur
        const needStable = cur.length < 40 ? 4 : cur.length < 200 ? 3 : 2;
        if (stableCount >= needStable) {
          // Double lecture anti-flicker
          await sleep(500);
          scrollChatToBottom();
          const again = snapshotThread();
          const a = normalizeForCompare(again.last || "");
          if (a && a !== baseLast && !isGenerating()) {
            // Préférer le plus long si stream a encore poussé
            const pick =
              (again.last || "").length >= (curRaw || "").length ? again.last : curRaw;
            log(
              "success",
              "Réponse OK stable (" +
                (pick || "").length +
                " car., asst=" +
                again.count +
                ", userTurn=" +
                sawUserTurn +
                ", gen=" +
                sawGenerating +
                ")"
            );
            return pick;
          }
          if (a === baseLast) {
            // Revenu à l'ancien — faux positif, continuer
            log("info", "Double-check: encore baseline — continue");
            sawGenuineChange = false;
            stableCount = 0;
            lastStable = "";
            continue;
          }
        }
      }

      // Fin de stream (stop disparu) + contenu nouveau
      if (
        readyToAccept &&
        sawGenerating &&
        !generating &&
        stableCount >= 1 &&
        cur.length > 3
      ) {
        await sleep(700);
        scrollChatToBottom();
        const again = snapshotThread();
        const a = normalizeForCompare(again.last || "");
        if (a && a !== baseLast && !isGenerating()) {
          const pick =
            (again.last || "").length >= cur.length ? again.last : curRaw;
          log("success", "Fin génération (" + (pick || "").length + " car.)");
          return pick;
        }
      }

      // Long stream qui a cessé de croître
      if (
        readyToAccept &&
        !generating &&
        stableCount >= 2 &&
        cur.length > 120 &&
        cur.length >= maxSeenLen &&
        growthTicks >= 1
      ) {
        await sleep(450);
        const again = snapshotThread();
        if (
          normalizeForCompare(again.last) === cur &&
          cur !== baseLast &&
          !isGenerating()
        ) {
          log("success", "Réponse figée (" + cur.length + " car.)");
          return again.last || curRaw;
        }
      }
    } else if (
      // Stream en place : dernier message s'allonge mais fingerprint change
      cur &&
      cur !== baseLast &&
      (sawUserTurn || genImpliesSend || sawGenerating)
    ) {
      // genuine aurait dû être true — forcer
      sawGenuineChange = true;
    }

    // Nouveau bloc vide en cours de génération
    if (snap.count > baseCount && generating) {
      sawGenuineChange = true;
    }

    await sleep(400);
  }

  // Timeout : uniquement si contenu ≠ baseline
  scrollChatToBottom();
  const finalSnap = snapshotThread();
  const finalNorm = normalizeForCompare(finalSnap.last || "");
  if (finalNorm && finalNorm !== baseLast) {
    log(
      "info",
      "Timeout partiel — last≠baseline (" + finalNorm.length + " car.)"
    );
    return finalSnap.last;
  }
  if (sawGenuineChange && lastStable && lastStable !== baseLast) {
    log("info", "Timeout partiel — lastStable (" + lastStable.length + ")");
    return lastStable;
  }
  throw new Error(
    "Timeout attente réponse assistant (baselineLen=" +
      (baseline.lastLen || 0) +
      " genuine=" +
      sawGenuineChange +
      " userTurn=" +
      sawUserTurn +
      " sawGen=" +
      sawGenerating +
      " lastStillBase=" +
      (finalNorm === baseLast) +
      ")"
  );
}

// ═══════════════════════════════════════════
// SEND (composer bas uniquement)
// ═══════════════════════════════════════════

async function actionSend(text) {

    // --- AUTO-SEND ADDON ---
    setTimeout(() => {
        const btn = findSendNear(document.querySelector('textarea')) || document.querySelector('div[role="button"][aria-label="Send"]');
        if (btn) {
            console.log("[NEMAPI] Clic automatique sur Envoi...");
            btn.click();
        }
    }, 800);

  log("info", "SEND — " + text.length + " car. (pas regenerate)");

  // Récupération si l'utilisateur a cliqué dans l'UI (menus, focus perdu…)
  let ready = await prepareChatForAutomation({ forceStop: false });
  if (!ready) {
    ready = await prepareChatForAutomation({ forceStop: true });
  }

  let input = findMainComposer();
  if (!input) throw new Error("Composer DeepSeek introuvable (UI bloquée ? fermez menus/modales)");

  // Génération en cours : attendre max 45s puis stop (évite hang post-clic)
  const tWait = Date.now();
  while (isGenerating() && Date.now() - tWait < 45000) {
    if (STOP_FLAG) throw new Error("stopped");
    await sleep(300);
  }
  if (isGenerating()) {
    log("info", "Génération encore active — stop pour libérer le composer");
    const stop = findStopButton();
    if (stop) {
      try {
        stop.click();
      } catch (e) {
        clickEl(stop);
      }
      await sleep(700);
    }
  }

  // Re-trouver le composer (DOM peut avoir changé après dismiss)
  input = findMainComposer();
  if (!input) {
    await prepareChatForAutomation({ forceStop: true });
    input = findMainComposer();
  }
  if (!input) throw new Error("Composer DeepSeek introuvable après récupération UI");

  if (!setNativeValue(input, text)) {
    throw new Error("Impossible d'écrire dans le composer");
  }
  await sleep(300);

  // Vérifier que le texte est bien dans le composer
  let got = getComposerText(input);
  if (text && got.length < Math.min(10, text.length) * 0.5) {
    // retry focus + inject
    try {
      input.focus();
    } catch (e) {}
    setNativeValue(input, text);
    await sleep(250);
    got = getComposerText(input);
  }
  if (text && got.length < Math.min(8, text.length) * 0.4) {
    // 2e essai après dismiss
    await dismissUiInterference();
    input = findMainComposer() || input;
    setNativeValue(input, text);
    await sleep(300);
    got = getComposerText(input);
  }
  if (text && got.length < Math.min(8, text.length) * 0.4) {
    throw new Error("Texte non injecté dans le composer (got=" + got.length + ")");
  }

  const beforeSnap = snapshotThread();
  const beforeCount = beforeSnap.count;
  const beforeLast = beforeSnap.last || "";

  // 1) Entrée d'abord : DeepSeek envoie le message du composer, pas un regen
  pressEnterToSend(input);
  await sleep(450);

  let afterText = getComposerText(input);
  let sent = afterText.trim().length < Math.min(20, text.length) * 0.35;

  // 2) Si le texte est toujours là → bouton send du COMPOSER uniquement
  if (!sent) {
    const sendBtn = findSendNear(input);
    if (sendBtn) {
      // Ne jamais scrollIntoView loin du bas (évite de cibler un bouton message)
      const r = sendBtn.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.55 || isMessageActionButton(sendBtn)) {
        log("info", "Bouton candidat rejeté (zone/action message) — retry Enter");
        pressEnterToSend(input);
      } else {
        log("info", "Clic send composer (lab=" + labelOf(sendBtn).slice(0, 50) + ")");
        // Clic sans scroll agressif vers le haut
        try {
          sendBtn.focus();
        } catch (e) {}
        try {
          sendBtn.click();
        } catch (e) {
          clickEl(sendBtn);
        }
      }
    } else {
      log("info", "Pas de bouton send sûr — 2e Enter");
      pressEnterToSend(input);
    }
    await sleep(500);
    afterText = getComposerText(input);
    sent = afterText.trim().length < Math.min(20, text.length) * 0.35;
  }

  // 3) Dernier recours : Enter encore une fois
  if (!sent) {
    log("info", "Composer encore plein — dernier Enter");
    pressEnterToSend(input);
    await sleep(600);
    afterText = getComposerText(input);
    sent = afterText.trim().length < Math.min(20, text.length) * 0.35;
  }

  // 4) Détecter un faux « regen » : génération sans vider le composer
  //    et sans nouveau message user → re-tenter send
  await sleep(400);
  if (!sent && isGenerating()) {
    const mid = getComposerText(input);
    if (mid.trim().length > 15) {
      log(
        "error",
        "Suspicion REGEN (génération + texte encore dans composer) — stop + re-send"
      );
      const stop = findStopButton();
      if (stop) {
        try {
          stop.click();
        } catch (e) {
          clickEl(stop);
        }
        await sleep(800);
      }
      // Re-injecter et Enter forcé
      setNativeValue(input, text);
      await sleep(200);
      pressEnterToSend(input);
      await sleep(500);
      afterText = getComposerText(input);
      sent = afterText.trim().length < Math.min(20, text.length) * 0.35;
    }
  }

  // 5) Si regen a démarré (composer vide mais last asst change sans new user turn)
  //    on laisse waitForAssistantResponse gérer — mais on log
  const afterSnap = snapshotThread();
  if (
    sent &&
    afterSnap.count === beforeCount &&
    isGenerating() &&
    normalizeForCompare(afterSnap.last) === normalizeForCompare(beforeLast)
  ) {
    log("info", "Génération en cours, même last asst — probablement stream en place");
  }

  if (!sent) {
    log(
      "info",
      "Avertissement: composer peut encore contenir du texte (" +
        afterText.length +
        " car.) — poursuite quand même"
    );
  } else {
    log("info", "Message envoyé (composer vidé / send OK)");
  }
}

// ═══════════════════════════════════════════
// FILE UPLOAD (UI DeepSeek)
// ═══════════════════════════════════════════

function findFileInputs() {
  return Array.from(document.querySelectorAll('input[type="file"]'));
}

function findAttachButton() {
  const keywords =
    /attach|upload|file|fichier|document|paperclip|clip|plus|ajouter|image|photo|附件|上传/i;
  const stop =
    /stop|send|envoyer|copy|edit|regenerat|new chat|nouveau|settings|param/i;
  const composer = findMainComposer();
  const zoneTop = composer
    ? composer.getBoundingClientRect().top - 80
    : window.innerHeight * 0.55;

  const candidates = Array.from(
    document.querySelectorAll("button, [role='button'], label, span, div")
  ).filter((el) => {
    if (!isVisible(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.top < zoneTop - 40) return false;
    if (r.width > 120 || r.height > 80) return false;
    return true;
  });

  let best = null;
  let bestScore = -1;
  for (const el of candidates) {
    const lab = labelOf(el);
    if (stop.test(lab) && !keywords.test(lab)) continue;
    if (!keywords.test(lab) && !el.querySelector("svg, img")) continue;
    let score = 0;
    if (keywords.test(lab)) score += 50;
    if (/attach|upload|file|paperclip|fichier|document/i.test(lab)) score += 80;
    if (el.tagName === "BUTTON" || el.getAttribute("role") === "button") score += 20;
    if (el.closest("label") && el.closest("label").querySelector('input[type="file"]'))
      score += 100;
    const r = el.getBoundingClientRect();
    if (composer) {
      const ir = composer.getBoundingClientRect();
      const d = Math.hypot(r.left - ir.left, r.top - ir.top);
      score += Math.max(0, 40 - d / 20);
    }
    if (score > bestScore) {
      bestScore = score;
      best = el;
    }
  }
  return best;
}

function waitForFileInput(timeoutMs) {
  const t0 = Date.now();
  return new Promise((resolve) => {
    const tick = () => {
      const inputs = findFileInputs();
      // préférer ceux avec accept documents/images ou multiple
      let pick =
        inputs.find((i) => !i.disabled) ||
        inputs[0] ||
        null;
      if (pick) {
        resolve(pick);
        return;
      }
      if (Date.now() - t0 >= timeoutMs) {
        resolve(null);
        return;
      }
      setTimeout(tick, 150);
    };
    tick();
  });
}

async function attachFilesToDeepSeek(files) {
  if (!files || !files.length) return { ok: true, attached: 0 };

  log("info", "Upload " + files.length + " fichier(s)");

  let input = findFileInputs().find((i) => !i.disabled) || null;

  if (!input) {
    const btn = findAttachButton();
    if (btn) {
      log("info", "Clic bouton attach");
      clickEl(btn);
      await sleep(400);
      // parfois un menu : cliquer "fichier" / "local"
      for (const el of document.querySelectorAll("button, [role='menuitem'], div, span, li")) {
        if (!isVisible(el)) continue;
        const lab = labelOf(el);
        if (/local|device|fichier|file|document|ordinateur|computer|从/i.test(lab)) {
          clickEl(el);
          await sleep(300);
          break;
        }
      }
    }
    input = await waitForFileInput(4000);
  }

  // Créer un input caché si l'UI n'en expose pas encore (certains SPA)
  if (!input) {
    input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.style.display = "none";
    document.body.appendChild(input);
    log("info", "input[type=file] synthétique créé");
  }

  const dt = new DataTransfer();
  for (const f of files) {
    const name = f.name || f.filename || "file.bin";
    const mime = f.mime || f.type || "application/octet-stream";
    const b64 = f.content_base64 || f.base64 || f.data || "";
    if (!b64) {
      log("error", "Fichier sans base64: " + name);
      continue;
    }
    const bytes = b64ToUint8Array(b64);
    const file = new File([bytes], name, { type: mime });
    dt.items.add(file);
    log("info", "  + " + name + " (" + bytes.length + " o, " + mime + ")");
  }

  if (!dt.files.length) throw new Error("Aucun fichier valide à attacher");

  try {
    input.files = dt.files;
  } catch (e) {
    // Firefox : parfois besoin de définir via prototype
    const desc = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "files"
    );
    if (desc && desc.set) desc.set.call(input, dt.files);
    else throw new Error("Impossible d'assigner input.files: " + e);
  }

  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  try {
    input.dispatchEvent(
      new CustomEvent("change", { bubbles: true, detail: { files: dt.files } })
    );
  } catch (e) {}

  // Attendre chip / preview fichier dans le composer
  const names = files.map((f) => f.name || f.filename || "").filter(Boolean);
  const t0 = Date.now();
  let previewOk = false;
  while (Date.now() - t0 < 12000) {
    const bodyText = document.body.innerText || "";
    if (names.some((n) => n && bodyText.includes(n.slice(0, Math.min(20, n.length))))) {
      previewOk = true;
      break;
    }
    // badges attach près du composer
    const chips = document.querySelectorAll(
      "[class*='file'], [class*='attach'], [class*='upload'], [class*='preview'], [class*='chip']"
    );
    if (chips.length > 0) {
      previewOk = true;
      break;
    }
    await sleep(300);
  }

  log(
    previewOk ? "success" : "info",
    previewOk
      ? "Fichier(s) attaché(s) (preview détectée)"
      : "Fichiers assignés (preview non confirmée — DeepSeek peut quand même les prendre)"
  );

  return { ok: true, attached: dt.files.length, preview: previewOk };
}

// ═══════════════════════════════════════════
// Job orchestration
// ═══════════════════════════════════════════

async function runJob(payload) {
  const jobId = payload.jobId;
  const force = !!(payload.force || (payload.meta && payload.meta.force));

  // Job coincé (souvent après clic UI + timeout partiel) : voler le verrou si vieux
  if (JOB_BUSY) {
    const age = JOB_BUSY_SINCE ? Date.now() - JOB_BUSY_SINCE : 0;
    if (force || age > 90000) {
      log(
        "info",
        "Job précédent encore marqué busy (age=" +
          Math.round(age / 1000) +
          "s) — force unlock"
      );
      forceUnlockJob("new job steals lock age=" + age);
      await sleep(600);
    } else {
      log("error", "Job déjà en cours — ignore " + String(jobId).substring(0, 8));
      browser.runtime.sendMessage({
        action: "automationError",
        jobId,
        error:
          "Extension occupée (job précédent encore en cours). Attendez ou renvoyez dans ~90s (auto-unlock).",
      });
      return;
    }
  }

  JOB_BUSY = true;
  STOP_FLAG = false;
  armJobWatchdog(jobId);

  const text = payload.text || payload.question || "";
  const meta = payload.meta || {};
  const files = meta.files || payload.files || [];
  const uploadOnly = !!(meta.upload_only || meta.uploadOnly || payload.upload_only);

  log(
    "job",
    "JOB " +
      String(jobId).substring(0, 8) +
      " mode=send files=" +
      (files.length || 0) +
      " uploadOnly=" +
      uploadOnly
  );

  try {
    // Toujours récupérer l'UI avant fichiers/envoi (clics manuels)
    await prepareChatForAutomation({
      forceStop: false,
      stopIfGenerating: true,
    });

    if (files.length) {
      await attachFilesToDeepSeek(files);
      await sleep(500);
    }

    if (uploadOnly && !String(text).trim()) {
      browser.runtime.sendMessage({
        action: "automationResult",
        jobId,
        result: JSON.stringify({
          ok: true,
          attached: files.length,
          message: "Fichier(s) attaché(s) au composer DeepSeek",
        }),
      });
      return;
    }

    if (String(text).trim()) {
      // Baseline JUSTE avant l'envoi (après attach) — empreinte last asst + users
      scrollChatToBottom();
      await sleep(200);
      const baseline = snapshotThread();
      log(
        "info",
        "Baseline asst=" +
          baseline.count +
          " user=" +
          baseline.userCount +
          " lastLen=" +
          baseline.lastLen
      );

      await actionSend(text);
      await sleep(600);

      // Attendre envoi réel : composer vide OU génération OU nouveau user
      const tGen = Date.now();
      while (Date.now() - tGen < 20000) {
        if (STOP_FLAG) throw new Error("stopped");
        if (isGenerating()) break;
        const s = snapshotThread();
        if (isGenuineNewAssistant(s, baseline)) break;
        if (userTurnConfirmed(s, baseline, extractUserNeedle(text))) break;
        const comp = findMainComposer();
        if (comp && getComposerText(comp).trim().length === 0 && Date.now() - tGen > 400) {
          // envoyé, attendre gen
          break;
        }
        await sleep(250);
      }

      const result = await waitForAssistantResponse(baseline, 480000, text);

      // Vérification finale anti-régression (ancienne réponse)
      const check = normalizeForCompare(result);
      const baseLast = normalizeForCompare(baseline.last || "");
      let finalResult = result;
      if (check && check === baseLast && (baseline.lastLen || 0) > 20) {
        log("error", "Réponse == baseline — re-attente 30s");
        try {
          finalResult = await waitForAssistantResponse(baseline, 30000, text);
        } catch (e) {
          throw new Error(
            "Réception a renvoyé l'ancienne réponse et re-attente échouée: " +
              (e && e.message ? e.message : e)
          );
        }
        if (
          normalizeForCompare(finalResult) === baseLast &&
          (baseline.lastLen || 0) > 20
        ) {
          throw new Error(
            "Réception instable: toujours l'ancienne réponse assistant (même empreinte)"
          );
        }
      }
      browser.runtime.sendMessage({
        action: "automationResult",
        jobId,
        result: finalResult,
      });
    } else if (files.length) {
      browser.runtime.sendMessage({
        action: "automationResult",
        jobId,
        result: JSON.stringify({
          ok: true,
          attached: files.length,
          message: "Fichier(s) attaché(s), aucun prompt",
        }),
      });
    } else {
      throw new Error("Job vide (pas de texte ni fichier)");
    }
  } catch (error) {
    const msg = error && error.message ? error.message : String(error);
    if (msg === "stopped") {
      browser.runtime.sendMessage({ action: "automationStopped", jobId });
    } else {
      log("error", msg);
      browser.runtime.sendMessage({
        action: "automationError",
        jobId,
        error: msg,
      });
    }
  } finally {
    JOB_BUSY = false;
    JOB_BUSY_SINCE = 0;
    clearJobWatchdog();
  }
}

// ═══════════════════════════════════════════
// Messaging
// ═══════════════════════════════════════════

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "runAutomation" || message.action === "runJob") {
    runJob({
      jobId: message.jobId,
      text: message.text || message.question,
      meta: message.meta,
      files: message.files,
      upload_only: message.upload_only,
      force: message.force,
    });
    sendResponse({ received: true, version: "2.7" });
  } else if (message.action === "stopAutomation") {
    STOP_FLAG = true;
    sendResponse({ received: true });
  } else if (message.action === "forceUnlock" || message.action === "resetBusy") {
    forceUnlockJob(message.reason || "manual");
    // Best-effort UI recovery (async, ne bloque pas la réponse)
    prepareChatForAutomation({ forceStop: true }).catch(() => {});
    sendResponse({ ok: true, version: "2.7", busy: JOB_BUSY });
  } else if (message.action === "prepareUi") {
    prepareChatForAutomation({ forceStop: !!message.forceStop })
      .then((ok) => sendResponse({ ok, version: "2.7" }))
      .catch((e) =>
        sendResponse({ ok: false, error: String(e && e.message ? e.message : e) })
      );
    return true;
  } else if (message.action === "ping") {
    sendResponse({
      pong: true,
      ready: true,
      version: "2.7",
      busy: JOB_BUSY,
      busyAgeMs: JOB_BUSY && JOB_BUSY_SINCE ? Date.now() - JOB_BUSY_SINCE : 0,
    });
  } else if (message.action === "probeDom") {
    const composer = findMainComposer();
    const snap = snapshotThread();
    const sendBtn = findSendNear(composer);
    const blockingModal = Array.from(
      document.querySelectorAll("[role='dialog'], [aria-modal='true']")
    ).some((el) => isVisible(el) && !el.querySelector("textarea"));
    sendResponse({
      input: !!composer,
      send: !!sendBtn,
      sendLabel: sendBtn ? labelOf(sendBtn).slice(0, 80) : "",
      sendIsMsgAction: sendBtn ? isMessageActionButton(sendBtn) : null,
      lastAsstLen: (snap.last || "").length,
      assistantCount: snap.count,
      userCount: snap.userCount,
      lastUserLen: snap.lastUserLen || 0,
      lastFp: (snap.lastFp || "").slice(0, 80),
      fileInputs: findFileInputs().length,
      attachBtn: !!findAttachButton(),
      generating: isGenerating(),
      busy: JOB_BUSY,
      busyAgeMs: JOB_BUSY && JOB_BUSY_SINCE ? Date.now() - JOB_BUSY_SINCE : 0,
      blockingModal,
      dsMessageCount: document.querySelectorAll(
        ".ds-message, [class*='ds-message']"
      ).length,
      version: "2.7",
    });
  }
  return true;
});

console.log(
  "[NEMAPI] Content script v2.7 (UI recovery post-clic + isGenerating strict + recv stable)"
);
} // guard
