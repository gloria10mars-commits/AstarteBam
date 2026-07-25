// ==UserScript==
// @name         NEMESIS v1.5 - Canaliseur IA
// @namespace    http://tampermonkey.net/
// @version      1.5
// @description  Vehicule de messages entre backend et sites d'IA - auto-register + bing MutationObserver
// @author       Nemesis
// @match        https://www.kimi.com/*
// @match        https://kimi.moonshot.cn/*
// @match        https://chat.deepseek.com/*
// @match        https://chat.qwen.ai/*
// @match        https://chat.qwenlm.ai/*
// @match        https://gemini.google.com/*
// @match        https://chatgpt.com/*
// @match        https://claude.ai/*
// @match        https://chat.mistral.ai/*
// @match        https://x.com/i/grok*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addStyle
// @connect      localhost
// @connect      127.0.0.1
// ==/UserScript==

(function() {
    'use strict';

    const BACKEND_URL = 'http://localhost:5000';
    const PAGE_ID = window.location.hostname.replace(/\./g, '_');

    let pollingInterval = null;
    let currentTaskId = null;
    let lastResponseText = '';
    let responseObserver = null;
    let bingSent = false;
    let responseStableSince = 0;
    let lastMutationTs = 0;

    // Configuration par defaut par site (utilisee si rien n'est sauvegarde)
    const SITE_CONFIGS = {
        'www_kimi_com': {
            input_click: [500, 650], send_click: [500, 730],
            copy_zone: [500, 350], wait_time: 8
        },
        'kimi_moonshot_cn': {
            input_click: [500, 650], send_click: [500, 730],
            copy_zone: [500, 350], wait_time: 8
        },
        'chat_deepseek_com': {
            input_click: [500, 650], send_click: [500, 730],
            copy_zone: [500, 350], wait_time: 8
        },
        'chat_qwen_ai': {
            input_click: [500, 650], send_click: [500, 730],
            copy_zone: [500, 350], wait_time: 8
        },
        'chat_qwenlm_ai': {
            input_click: [500, 650], send_click: [500, 730],
            copy_zone: [500, 350], wait_time: 8
        },
        'gemini_google_com': {
            input_click: [450, 600], send_click: [450, 680],
            copy_zone: [450, 300], wait_time: 6
        }
    };

    // =========================================================
    // Styles
    // =========================================================
    GM_addStyle(`
        #nemesis-indicator {
            position: fixed; top: 10px; right: 10px;
            background: #00ff88; color: #000;
            padding: 5px 12px; border-radius: 20px;
            font-size: 12px; font-weight: bold;
            z-index: 99999; font-family: monospace;
            opacity: 0.85; cursor: pointer;
            transition: all 0.3s; user-select: none;
        }
        #nemesis-indicator.working {
            background: #ff8800; animation: nemesis-pulse 1s infinite;
        }
        #nemesis-indicator.done { background: #00ccff; }
        #nemesis-indicator.error { background: #ff4488; color: #fff; }
        #nemesis-indicator.registered::before { content: "🟢 "; }
        #nemesis-indicator.unregistered::before { content: "🔴 "; }
        @keyframes nemesis-pulse {
            0% { opacity: 0.85; } 50% { opacity: 1; } 100% { opacity: 0.85; }
        }
        #nemesis-config-panel {
            position: fixed; top: 50px; right: 10px;
            background: #1a1a2e; color: #fff;
            padding: 15px; border-radius: 10px;
            z-index: 99998; font-family: monospace; font-size: 12px;
            display: none; min-width: 280px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.5);
        }
        #nemesis-config-panel input {
            width: 60px; background: #2a2a4e;
            border: 1px solid #444; color: #fff;
            padding: 3px; margin: 2px; border-radius: 3px;
        }
        #nemesis-config-panel button {
            background: #00ff88; color: #000; border: none;
            padding: 5px 10px; border-radius: 3px;
            cursor: pointer; margin: 3px; font-weight: bold;
        }
        #nemesis-toast {
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: #1a1a2e; color: #00ff88;
            padding: 10px 20px; border-radius: 8px;
            z-index: 99999; font-family: monospace; font-size: 13px;
            opacity: 0; transition: opacity 0.3s;
            box-shadow: 0 5px 20px rgba(0,0,0,0.5);
        }
        #nemesis-toast.show { opacity: 1; }
    `);

    // =========================================================
    // UI elements
    // =========================================================
    const indicator = document.createElement('div');
    indicator.id = 'nemesis-indicator';
    indicator.className = 'unregistered';
    indicator.textContent = '⚡ NEMESIS';
    document.body.appendChild(indicator);

    const toast = document.createElement('div');
    toast.id = 'nemesis-toast';
    document.body.appendChild(toast);

    function showToast(msg, ms = 2500) {
        toast.textContent = msg;
        toast.classList.add('show');
        clearTimeout(showToast._t);
        showToast._t = setTimeout(() => toast.classList.remove('show'), ms);
    }

    let captureMode = null;
    const configPanel = document.createElement('div');
    configPanel.id = 'nemesis-config-panel';
    configPanel.innerHTML = `
        <div><strong>🎯 Config ${PAGE_ID}</strong></div>
        <div style="margin:6px 0;">
            <button id="nm-btn-input">🖱️ Zone saisie</button>
            <span id="nm-input-val" style="color:#ff8800;">non défini</span>
        </div>
        <div style="margin:6px 0;">
            <button id="nm-btn-send">🚀 Bouton envoyer</button>
            <span id="nm-send-val" style="color:#00ccff;">non défini</span>
        </div>
        <div style="margin:6px 0;">
            <button id="nm-btn-copy">📋 Zone réponse</button>
            <span id="nm-copy-val" style="color:#ff4488;">non défini</span>
        </div>
        <div>Wait(s):<input id="nm-wait" type="number" value="8" style="width:50px"></div>
        <div style="margin-top:8px;">
            <button id="nm-save-config">💾 Sauver</button>
            <button id="nm-test">🧪 Test</button>
            <button id="nm-clear">🗑️ Effacer</button>
        </div>
        <div id="nm-status" style="margin-top:8px;color:#00ff88;"></div>
        <hr style="border-color:#444;margin:8px 0;">
        <div style="font-size:11px;color:#aaa;">
            Statut: <span id="nm-stat-statut">inconnu</span><br>
            Backend: <span id="nm-stat-backend">inconnu</span><br>
            Tâche: <span id="nm-stat-task">aucune</span>
        </div>
    `;
    document.body.appendChild(configPanel);

    const captureCursor = document.createElement('div');
    captureCursor.id = 'nemesis-capture-cursor';
    captureCursor.style.cssText = `
        display:none; position:fixed; pointer-events:none; z-index:999999;
        width:30px; height:30px; border:3px dashed red; border-radius:50%;
        transform:translate(-50%,-50%); animation: nem-spin 1s linear infinite;
    `;
    document.body.appendChild(captureCursor);
    GM_addStyle('@keyframes nem-spin { 100% { transform:translate(-50%,-50%) rotate(360deg); } }');

    indicator.addEventListener('click', () => {
        configPanel.style.display = configPanel.style.display === 'none' ? 'block' : 'none';
    });

    // =========================================================
    // Coords + persistance (GM_setValue)
    // =========================================================
    let coords = { input: null, send: null, copy: null };

    function updateDisplay() {
        const fmt = c => c ? `${c[0]},${c[1]}` : 'non défini';
        document.getElementById('nm-input-val').textContent = fmt(coords.input);
        document.getElementById('nm-send-val').textContent = fmt(coords.send);
        document.getElementById('nm-copy-val').textContent = fmt(coords.copy);
    }

    function getConfig() {
        const saved = GM_getValue('config_' + PAGE_ID);
        if (saved) {
            try {
                const cfg = JSON.parse(saved);
                coords.input = cfg.input_click || null;
                coords.send = cfg.send_click || null;
                coords.copy = cfg.copy_zone || null;
                updateDisplay();
                const w = document.getElementById('nm-wait');
                if (w) w.value = cfg.wait_time || 8;
                return cfg;
            } catch (e) {
                console.warn('[NEMESIS] config corrompue', e);
            }
        }
        return SITE_CONFIGS[PAGE_ID] || {
            input_click: [400, 700],
            send_click: [400, 780],
            copy_zone: [400, 400],
            wait_time: 8
        };
    }

    function saveConfigLocal(config) {
        GM_setValue('config_' + PAGE_ID, JSON.stringify(config));
        console.log('[NEMESIS] Config sauvee localement pour', PAGE_ID);
    }

    function clearConfigLocal() {
        GM_deleteValue && GM_deleteValue('config_' + PAGE_ID);
        coords = { input: null, send: null, copy: null };
        updateDisplay();
        showToast('🗑️ Config effacée');
    }

    // =========================================================
    // Capture mode
    // =========================================================
    function startCapture(mode) {
        captureMode = mode;
        captureCursor.style.display = 'block';
        document.body.style.cursor = 'crosshair';
        document.getElementById('nm-status').textContent = '🎯 Clique sur la page pour capturer...';
        configPanel.style.display = 'none';
        ['nm-btn-input','nm-btn-send','nm-btn-copy'].forEach(id => {
            document.getElementById(id).style.opacity = '0.5';
        });
        document.getElementById('nm-btn-' + mode).style.opacity = '1';
    }

    function stopCapture() {
        captureMode = null;
        captureCursor.style.display = 'none';
        document.body.style.cursor = '';
        configPanel.style.display = 'block';
        ['nm-btn-input','nm-btn-send','nm-btn-copy'].forEach(id => {
            document.getElementById(id).style.opacity = '1';
        });
    }

    document.addEventListener('mousemove', (e) => {
        if (captureMode) {
            captureCursor.style.left = e.clientX + 'px';
            captureCursor.style.top = e.clientY + 'px';
        }
    });

    document.addEventListener('click', (e) => {
        if (!captureMode) return;
        e.preventDefault();
        e.stopPropagation();
        coords[captureMode] = [e.clientX, e.clientY];
        updateDisplay();
        document.getElementById('nm-status').textContent =
            `✅ ${captureMode.toUpperCase()} capturé: ${e.clientX},${e.clientY}`;
        stopCapture();
    }, true);

    // =========================================================
    // Boutons
    // =========================================================
    document.getElementById('nm-btn-input').addEventListener('click', (e) => {
        e.stopPropagation(); startCapture('input');
    });
    document.getElementById('nm-btn-send').addEventListener('click', (e) => {
        e.stopPropagation(); startCapture('send');
    });
    document.getElementById('nm-btn-copy').addEventListener('click', (e) => {
        e.stopPropagation(); startCapture('copy');
    });

    document.getElementById('nm-save-config').addEventListener('click', () => {
        if (!coords.input || !coords.send || !coords.copy) {
            document.getElementById('nm-status').textContent = '⚠️ Définis les 3 points d\'abord !';
            return;
        }
        const config = {
            input_click: coords.input,
            send_click: coords.send,
            copy_zone: coords.copy,
            wait_time: parseInt(document.getElementById('nm-wait').value) || 8
        };
        saveConfigLocal(config);
        registerPage(config, () => {
            document.getElementById('nm-status').textContent = '✅ Config sauvée et enregistrée!';
            showToast('✅ Calibrage sauvegardé pour ' + PAGE_ID);
            indicator.classList.remove('unregistered');
            indicator.classList.add('registered');
        });
    });

    document.getElementById('nm-test').addEventListener('click', () => {
        const config = getConfig();
        registerPage(config, () => {
            sendTestPrompt(config);
        });
        document.getElementById('nm-status').textContent = '🔍 Test lancé...';
    });

    document.getElementById('nm-clear').addEventListener('click', () => {
        if (confirm('Effacer la config pour ' + PAGE_ID + ' ?')) {
            clearConfigLocal();
        }
    });

    // =========================================================
    // Communication backend
    // =========================================================
    function registerPage(config, cb) {
        const cfg = config || getConfig();
        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/register_page',
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({ page_id: PAGE_ID, config: cfg }),
            onload: function(resp) {
                try {
                    const data = JSON.parse(resp.responseText);
                    console.log('[NEMESIS] Page enregistrée:', data);
                    indicator.classList.remove('unregistered');
                    indicator.classList.add('registered');
                    if (cb) cb(data);
                } catch(e) {
                    console.error('[NEMESIS] parse register', e);
                    indicator.classList.add('error');
                }
            },
            onerror: function() {
                console.error('[NEMESIS] backend injoignable');
                indicator.classList.add('error');
                indicator.classList.remove('registered');
                indicator.classList.add('unregistered');
                showToast('❌ Backend injoignable sur ' + BACKEND_URL);
            }
        });
    }

    function sendTestPrompt(config) {
        const taskId = 'manual_test_' + Date.now();
        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/send_prompt',
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                page_id: PAGE_ID,
                prompt: 'Salut, réponds en une phrase courte.',
                config: config || getConfig(),
                task_id: taskId
            }),
            onload: function(resp) {
                try {
                    const data = JSON.parse(resp.responseText);
                    if (data.task_id) {
                        currentTaskId = data.task_id;
                        indicator.classList.add('working');
                        indicator.textContent = '⏳ Travail...';
                        startResponseWatcher();
                        showToast('⏳ Tâche ' + currentTaskId);
                    }
                } catch(e) {}
            }
        });
    }

    // =========================================================
    // Response watcher (MutationObserver + detection fin)
    // =========================================================
    function findResponseContainer() {
        // Heuristique: cherche les conteneurs typiques de chat
        const candidates = [
            document.querySelector('[data-testid="conversation"]'),
            document.querySelector('[class*="conversation"]'),
            document.querySelector('[class*="messages"]'),
            document.querySelector('main'),
            document.querySelector('[class*="chat-content"]'),
            document.querySelector('[class*="response"]'),
            document.querySelector('[class*="markdown"]')?.parentElement
        ].filter(Boolean);
        return candidates[0] || document.body;
    }

    function getLatestResponseText() {
        // Recupere le dernier bloc de texte de reponse
        const container = findResponseContainer();
        // Cherche le dernier enfant avec du texte substantiel
        const children = container.querySelectorAll('div, p, article, section');
        let best = '';
        for (const c of children) {
            const txt = c.innerText || c.textContent || '';
            if (txt.length > best.length && txt.length < 100000) {
                best = txt;
            }
        }
        return best.trim();
    }

    function startResponseWatcher() {
        if (responseObserver) responseObserver.disconnect();
        bingSent = false;
        lastResponseText = '';
        responseStableSince = 0;
        lastMutationTs = Date.now();

        const container = findResponseContainer();
        responseObserver = new MutationObserver(() => {
            lastMutationTs = Date.now();
            const current = getLatestResponseText();
            if (current && current !== lastResponseText && current.length > 2) {
                lastResponseText = current;
                responseStableSince = 0;
            }
        });
        responseObserver.observe(container, {
            childList: true, subtree: true, characterData: true
        });
        console.log('[NEMESIS] MutationObserver demarre sur', container);

        // Boucle de check: si pas de mutation depuis 2s et qu'on a du texte, on envoie le bing
        const checker = setInterval(() => {
            if (bingSent || !currentTaskId) {
                clearInterval(checker);
                return;
            }
            const stableFor = Date.now() - lastMutationTs;
            if (lastResponseText && stableFor > 2000 && lastResponseText.length > 5) {
                // La reponse est stable depuis 2s -> on considere que c'est fini
                console.log('[NEMESIS] Reponse stable, envoi bing');
                clearInterval(checker);
                sendBing(lastResponseText);
            }
        }, 500);

        // Timeout: 60s max
        setTimeout(() => {
            if (!bingSent && currentTaskId) {
                clearInterval(checker);
                console.warn('[NEMESIS] Timeout watcher, envoi partiel');
                if (lastResponseText) sendBing(lastResponseText);
                else sendBingError('Timeout: pas de reponse detectee');
            }
        }, 60000);
    }

    function sendBing(content) {
        if (bingSent) return;
        bingSent = true;
        if (responseObserver) { responseObserver.disconnect(); responseObserver = null; }

        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/bing/' + PAGE_ID,
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                content: content,
                task_id: currentTaskId,
                success: true
            }),
            onload: function() {
                console.log('[NEMESIS] Bing envoye:', content.substring(0, 100));
                indicator.classList.remove('working');
                indicator.classList.add('done');
                indicator.textContent = '✅ Fini';
                showToast('📥 Réponse: ' + content.substring(0, 60) + '...', 4000);
                setTimeout(() => {
                    indicator.classList.remove('done');
                    indicator.textContent = '⚡ NEMESIS';
                    currentTaskId = null;
                }, 3000);
            }
        });
    }

    function sendBingError(msg) {
        if (bingSent) return;
        bingSent = true;
        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/bing/' + PAGE_ID,
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                content: '',
                task_id: currentTaskId,
                success: false,
                error: msg
            }),
            onload: function() {
                indicator.classList.remove('working');
                indicator.classList.add('error');
                indicator.textContent = '❌ Erreur';
                setTimeout(() => {
                    indicator.classList.remove('error');
                    indicator.textContent = '⚡ NEMESIS';
                    currentTaskId = null;
                }, 3000);
            }
        });
    }

    // =========================================================
    // Intercepter Ctrl+C (backup si MutationObserver rate)
    // =========================================================
    document.addEventListener('copy', function(e) {
        const selection = window.getSelection().toString().trim();
        if (selection.length > 10 && currentTaskId && !bingSent) {
            console.log('[NEMESIS] Copie manuelle détectée');
            sendBing(selection);
        }
    });

    // =========================================================
    // Statut panel
    // =========================================================
    function updateStatut() {
        const statutEl = document.getElementById('nm-stat-statut');
        const backendEl = document.getElementById('nm-stat-backend');
        const taskEl = document.getElementById('nm-stat-task');
        if (statutEl) statutEl.textContent = currentTaskId ? 'occupé' : 'prêt';
        if (taskEl) taskEl.textContent = currentTaskId || 'aucune';

        // Ping backend
        GM_xmlhttpRequest({
            method: 'GET',
            url: BACKEND_URL + '/health',
            timeout: 2000,
            onload: function(r) {
                try {
                    const h = JSON.parse(r.responseText);
                    if (backendEl) backendEl.textContent =
                        (h.xdotool ? '✓' : '✗') + ' xdotool / ' +
                        (h.xclip ? '✓' : '✗') + ' xclip / ' +
                        (h.display || 'no DISPLAY');
                } catch(e) {
                    if (backendEl) backendEl.textContent = 'réponse invalide';
                }
            },
            onerror: function() {
                if (backendEl) backendEl.textContent = 'injoignable';
            }
        });
    }
    setInterval(updateStatut, 5000);

    // =========================================================
    // Init: auto-register si config sauvee
    // =========================================================
    function init() {
        const config = getConfig();
        const hasSavedConfig = !!GM_getValue('config_' + PAGE_ID);
        if (hasSavedConfig) {
            console.log('[NEMESIS] Config trouvee pour', PAGE_ID, '- auto-register');
            registerPage(config, () => {
                showToast('✅ ' + PAGE_ID + ' auto-enregistré', 2000);
            });
        } else {
            console.log('[NEMESIS] Pas de config sauvee pour', PAGE_ID, '- calibration requise');
            indicator.classList.add('unregistered');
            showToast('🔴 Clique ⚡ NEMESIS (haut droite) pour calibrer', 5000);
        }
        updateStatut();
    }

    // Attendre que le DOM soit pret
    if (document.body) init();
    else document.addEventListener('DOMContentLoaded', init);

})();
