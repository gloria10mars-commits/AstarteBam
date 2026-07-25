// ==UserScript==
// @name         NEMESIS - Canaliseur IA
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Véhicule de messages entre le backend et les sites d'IA
// @author       Nemesis
// @match        https://kimi.moonshot.cn/*
// @match        https://chat.deepseek.com/*
// @match        https://chat.qwenlm.ai/*
// @match        https://gemini.google.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addStyle
// ==/UserScript==

(function() {
    'use strict';

    const BACKEND_URL = 'http://localhost:5000';
    const PAGE_ID = window.location.hostname.replace(/\./g, '_');
    let pollingInterval = null;
    let currentTaskId = null;

    // Configuration par défaut par site (à calibrer avec 📍 Position souris)
    const SITE_CONFIGS = {
        'kimi_moonshot_cn': {
            input_click: [500, 650],
            send_click: [500, 730],
            copy_zone: [500, 350],
            wait_time: 8
        },
        'chat_deepseek_com': {
            input_click: [500, 650],
            send_click: [500, 730],
            copy_zone: [500, 350],
            wait_time: 8
        },
        'chat_qwenlm_ai': {
            input_click: [500, 650],
            send_click: [500, 730],
            copy_zone: [500, 350],
            wait_time: 8
        },
        'gemini_google_com': {
            input_click: [450, 600],
            send_click: [450, 680],
            copy_zone: [450, 300],
            wait_time: 6
        }
    };

    // Style discret pour l'indicateur
    GM_addStyle(`
        #nemesis-indicator {
            position: fixed;
            top: 10px;
            right: 10px;
            background: #00ff88;
            color: #000;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            z-index: 99999;
            font-family: monospace;
            opacity: 0.8;
            cursor: pointer;
            transition: all 0.3s;
        }
        #nemesis-indicator.working {
            background: #ff8800;
            animation: pulse 1s infinite;
        }
        #nemesis-indicator.done {
            background: #00ccff;
        }
        @keyframes pulse {
            0% { opacity: 0.8; }
            50% { opacity: 1; }
            100% { opacity: 0.8; }
        }
        #nemesis-config-panel {
            position: fixed;
            top: 50px;
            right: 10px;
            background: #1a1a2e;
            color: #fff;
            padding: 15px;
            border-radius: 10px;
            z-index: 99998;
            font-family: monospace;
            font-size: 12px;
            display: none;
            min-width: 250px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.5);
        }
        #nemesis-config-panel input {
            width: 60px;
            background: #2a2a4e;
            border: 1px solid #444;
            color: #fff;
            padding: 3px;
            margin: 2px;
            border-radius: 3px;
        }
        #nemesis-config-panel button {
            background: #00ff88;
            color: #000;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            margin: 3px;
        }
    `);

    // Créer l'indicateur
    const indicator = document.createElement('div');
    indicator.id = 'nemesis-indicator';
    indicator.textContent = '⚡ NEMESIS';
    document.body.appendChild(indicator);

    let captureMode = null; // 'input', 'send', 'copy', ou null

    // Panneau de configuration (accessible en cliquant sur l'indicateur)
    const configPanel = document.createElement('div');
    configPanel.id = 'nemesis-config-panel';
    configPanel.innerHTML = `
        <div><strong>🎯 Config ${PAGE_ID}</strong></div>
        <div style="margin-bottom:6px;">
            <button id="nm-btn-input" style="background:#ff8800;color:#000;border:none;padding:5px 10px;border-radius:3px;cursor:pointer;font-weight:bold;">🖱️ Zone saisie</button>
            <span id="nm-input-val" style="color:#ff8800;">non défini</span>
        </div>
        <div style="margin-bottom:6px;">
            <button id="nm-btn-send" style="background:#00ccff;color:#000;border:none;padding:5px 10px;border-radius:3px;cursor:pointer;font-weight:bold;">🚀 Bouton envoyer</button>
            <span id="nm-send-val" style="color:#00ccff;">non défini</span>
        </div>
        <div style="margin-bottom:6px;">
            <button id="nm-btn-copy" style="background:#ff4488;color:#000;border:none;padding:5px 10px;border-radius:3px;cursor:pointer;font-weight:bold;">📋 Zone réponse</button>
            <span id="nm-copy-val" style="color:#ff4488;">non défini</span>
        </div>
        <div>Wait(s):<input id="nm-wait" type="number" value="8" style="width:50px"></div>
        <button id="nm-save-config" style="margin-top:8px;">💾 Sauver</button>
        <button id="nm-test" style="margin-top:8px;">🧪 Test</button>
        <div id="nm-status" style="margin-top:8px;color:#00ff88;"></div>
    `;
    document.body.appendChild(configPanel);

    // Curseur de capture
    const captureCursor = document.createElement('div');
    captureCursor.id = 'nemesis-capture-cursor';
    captureCursor.style.cssText = `
        display:none; position:fixed; pointer-events:none; z-index:999999;
        width:30px; height:30px; border:3px dashed red; border-radius:50%;
        transform:translate(-50%,-50%); animation: spin 1s linear infinite;
    `;
    document.body.appendChild(captureCursor);
    GM_addStyle('@keyframes spin { 100% { transform:translate(-50%,-50%) rotate(360deg); } }');

    // Toggle panneau de config
    indicator.addEventListener('click', () => {
        configPanel.style.display = configPanel.style.display === 'none' ? 'block' : 'none';
    });

    // Coordonnées temporaires
    let coords = { input: null, send: null, copy: null };

    function updateDisplay() {
        document.getElementById('nm-input-val').textContent = coords.input ? `${coords.input[0]},${coords.input[1]}` : 'non défini';
        document.getElementById('nm-send-val').textContent = coords.send ? `${coords.send[0]},${coords.send[1]}` : 'non défini';
        document.getElementById('nm-copy-val').textContent = coords.copy ? `${coords.copy[0]},${coords.copy[1]}` : 'non défini';
    }

    function startCapture(mode) {
        captureMode = mode;
        captureCursor.style.display = 'block';
        document.body.style.cursor = 'crosshair';
        document.getElementById('nm-status').textContent = '🎯 Clique sur la page pour capturer...';
        configPanel.style.display = 'none';

        // Met en valeur le bouton actif
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

    // Suivi souris pour le curseur de capture
    document.addEventListener('mousemove', (e) => {
        if (captureMode) {
            captureCursor.style.left = e.clientX + 'px';
            captureCursor.style.top = e.clientY + 'px';
        }
    });

    // Capture au clic
    document.addEventListener('click', (e) => {
        if (!captureMode) return;
        e.preventDefault();
        e.stopPropagation();

        coords[captureMode] = [e.clientX, e.clientY];
        updateDisplay();
        document.getElementById('nm-status').textContent = `✅ ${captureMode.toUpperCase()} capturé: ${e.clientX},${e.clientY}`;
        stopCapture();
    }, true);

    // Boutons de capture
    document.getElementById('nm-btn-input').addEventListener('click', (e) => {
        e.stopPropagation();
        startCapture('input');
    });
    document.getElementById('nm-btn-send').addEventListener('click', (e) => {
        e.stopPropagation();
        startCapture('send');
    });
    document.getElementById('nm-btn-copy').addEventListener('click', (e) => {
        e.stopPropagation();
        startCapture('copy');
    });

    // Sauvegarder la config
    document.getElementById('nm-save-config').addEventListener('click', () => {
        if (!coords.input || !coords.send || !coords.copy) {
            document.getElementById('nm-status').textContent = '⚠️ Définis les 3 boutons d\'abord !';
            return;
        }
        const config = {
            input_click: coords.input,
            send_click: coords.send,
            copy_zone: coords.copy,
            wait_time: parseInt(document.getElementById('nm-wait').value)
        };
        GM_setValue('config_' + PAGE_ID, JSON.stringify(config));
        document.getElementById('nm-status').textContent = '✅ Config sauvée!';
        registerPage(config);
    });

    // Test
    document.getElementById('nm-test').addEventListener('click', () => {
        const config = getConfig();
        registerPage(config);
        setTimeout(() => pollForTask(config), 500);
        document.getElementById('nm-status').textContent = '🔍 Test lancé...';
    });

    // Charger la config sauvegardée
    function getConfig() {
        const saved = GM_getValue('config_' + PAGE_ID);
        if (saved) {
            const config = JSON.parse(saved);
            coords.input = config.input_click;
            coords.send = config.send_click;
            coords.copy = config.copy_zone;
            updateDisplay();
            document.getElementById('nm-wait').value = config.wait_time;
            return config;
        }
        const def = SITE_CONFIGS[PAGE_ID];
        if (def) {
            coords.input = def.input_click;
            coords.send = def.send_click;
            coords.copy = def.copy_zone;
            updateDisplay();
        }
        return def || {
            input_click: [400, 700],
            send_click: [400, 780],
            copy_zone: [400, 400],
            wait_time: 8
        };
    }

    // Enregistrer la page auprès du backend
    function registerPage(config) {
        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/register_page',
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                page_id: PAGE_ID,
                config: config || getConfig()
            }),
            onload: function(resp) {
                console.log('[NEMESIS] Page enregistrée:', resp.responseText);
                document.getElementById('nm-status').textContent = '📡 Page enregistrée';
            },
            onerror: function(err) {
                console.error('[NEMESIS] Erreur enregistrement:', err);
                document.getElementById('nm-status').textContent = '❌ Erreur connexion';
            }
        });
    }

    // Polling: vérifie si une tâche est en attente
    function pollForTask(config) {
        if (currentTaskId) return; // déjà en cours

        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/send_prompt',
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                page_id: PAGE_ID,
                prompt: 'test_ping',
                config: config || getConfig(),
                task_id: 'manual_test_' + Date.now()
            }),
            onload: function(resp) {
                try {
                    const data = JSON.parse(resp.responseText);
                    if (data.task_id) {
                        currentTaskId = data.task_id;
                        indicator.classList.add('working');
                        indicator.textContent = '⏳ Travail...';
                        document.getElementById('nm-status').textContent = '⚙️ Exécution...';
                        // Lancer un scan rapide pour détecter le résultat
                        setTimeout(() => checkResult(), config.wait_time * 1000 + 2000);
                    }
                } catch(e) {}
            }
        });
    }

    // Vérifier le résultat
    function checkResult() {
        if (!currentTaskId) return;

        GM_xmlhttpRequest({
            method: 'GET',
            url: BACKEND_URL + '/get_result/' + currentTaskId,
            onload: function(resp) {
                try {
                    const data = JSON.parse(resp.responseText);
                    if (data.success !== undefined) {
                        indicator.classList.remove('working');
                        indicator.classList.add('done');
                        indicator.textContent = '✅ Fini';
                        document.getElementById('nm-status').textContent = '📋 Résultat prêt';
                        // Envoyer le bing avec le contenu
                        sendBing(data.result || '');
                        setTimeout(() => {
                            indicator.classList.remove('done');
                            indicator.textContent = '⚡ NEMESIS';
                            currentTaskId = null;
                        }, 3000);
                    } else {
                        setTimeout(() => checkResult(), 1000);
                    }
                } catch(e) {
                    setTimeout(() => checkResult(), 1000);
                }
            },
            onerror: () => setTimeout(() => checkResult(), 2000)
        });
    }

    // Envoyer un "bing" (données copiées) au backend
    function sendBing(content) {
        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL + '/bing/' + PAGE_ID,
            headers: {'Content-Type': 'application/json'},
            data: JSON.stringify({
                content: content,
                task_id: currentTaskId
            }),
            onload: function() {
                console.log('[NEMESIS] Bing envoyé:', content.substring(0, 100) + '...');
            }
        });
    }

    // Intercepter Ctrl+C pour notifier le backend
    document.addEventListener('copy', function(e) {
        const selection = window.getSelection().toString().trim();
        if (selection.length > 10 && currentTaskId) {
            console.log('[NEMESIS] Copie détectée:', selection.substring(0, 100) + '...');
            sendBing(selection);
        }
    });

    // Démarrer
    function init() {
        const config = getConfig();
        registerPage(config);
        console.log('[NEMESIS] Initialisé sur', PAGE_ID, 'avec config:', config);
    }

    init();

})();
