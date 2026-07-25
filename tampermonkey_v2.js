// ==UserScript==
// @name         AstarteBam v6.0 — Worker Autonome
// @namespace    astartebam
// @version      6.0
// @description  Worker Tampermonkey pour AstarteBam - scrape les LLM gratuits
// @match        *://chat.deepseek.com/*
// @match        *://chatgpt.com/*
// @match        *://claude.ai/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @connect      *
// ==/UserScript==

(function() {
    'use strict';

    // ═══════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════
    var SERVER = 'http://127.0.0.1:8765';
    var POLL_INTERVAL = 3000;       // ms entre chaque check
    var MAX_IDLE_WAIT = 120000;     // 2 min max sans prompt avant de ralentir

    // ═══════════════════════════════════
    // UTILITAIRES
    // ═══════════════════════════════════
    function log(msg) {
        console.log('[AstarteBam] ' + msg);
    }

    function apiCall(method, path, data, callback) {
        var url = SERVER + path;
        var opts = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            onload: function(resp) {
                try {
                    var result = JSON.parse(resp.responseText);
                    callback(null, result);
                } catch(e) {
                    callback(e, null);
                }
            },
            onerror: function(err) {
                callback(err, null);
            }
        };
        if (data && method === 'POST') {
            opts.data = JSON.stringify(data);
        }
        GM_xmlhttpRequest(opts);
    }

    // ═══════════════════════════════════
    // EXTRACT JSON FROM LLM RESPONSE
    // ═══════════════════════════════════
    function extractJsonBlocks(text) {
        var results = [];
        var pattern = /```json\s*([\s\S]*?)```/g;
        var match;
        while ((match = pattern.exec(text)) !== null) {
            try {
                var parsed = JSON.parse(match[1].trim());
                if (parsed.version === 1 && parsed.actions) {
                    results.push(parsed);
                }
            } catch(e) {}
        }
        if (results.length === 0) {
            try {
                var trimmed = text.trim().replace(/^```\w*\s*/, '').replace(/\s*```$/, '');
                var parsed = JSON.parse(trimmed);
                if (parsed.version === 1 && parsed.actions) {
                    results.push(parsed);
                }
            } catch(e) {}
        }
        return results;
    }

    // ═══════════════════════════════════
    // SITE-SPECIFIC SCRAPERS
    // ═══════════════════════════════════
    var scrapers = {
        deepseek: {
            findTextarea: function() {
                return document.querySelector('textarea') ||
                       document.querySelector('[contenteditable="true"]');
            },
            findSendButton: function() {
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].innerText && (btns[i].innerText.includes('Send') || btns[i].innerHTML.includes('svg'))) {
                        return btns[i];
                    }
                }
                return null;
            },
            findResponse: function() {
                var msgs = document.querySelectorAll('[class*="message"], [class*="assistant"], [class*="response"]');
                if (msgs.length > 0) {
                    return msgs[msgs.length - 1].innerText;
                }
                return null;
            },
            isGenerating: function() {
                var btn = document.querySelector('button[class*="stop"]');
                return btn !== null;
            }
        },
        chatgpt: {
            findTextarea: function() {
                return document.querySelector('#prompt-textarea') ||
                       document.querySelector('textarea');
            },
            findSendButton: function() {
                return document.querySelector('[data-testid="send-button"]');
            },
            findResponse: function() {
                var msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                if (msgs.length > 0) {
                    return msgs[msgs.length - 1].innerText;
                }
                return null;
            },
            isGenerating: function() {
                return document.querySelector('[data-testid="stop-button"]') !== null;
            }
        },
        claude: {
            findTextarea: function() {
                return document.querySelector('[contenteditable="true"]') ||
                       document.querySelector('textarea');
            },
            findSendButton: function() {
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].ariaLabel && btns[i].ariaLabel.includes('Send')) {
                        return btns[i];
                    }
                }
                return null;
            },
            findResponse: function() {
                var msgs = document.querySelectorAll('[class*="prose"]');
                if (msgs.length > 0) {
                    return msgs[msgs.length - 1].innerText;
                }
                return null;
            },
            isGenerating: function() {
                return document.querySelector('[class*="cursor"]') !== null ||
                       document.querySelector('button[class*="stop"]') !== null;
            }
        }
    };

    function getCurrentScraper() {
        if (location.hostname.includes('deepseek')) return scrapers.deepseek;
        if (location.hostname.includes('chatgpt') || location.hostname.includes('openai')) return scrapers.chatgpt;
        if (location.hostname.includes('claude')) return scrapers.claude;
        return null;
    }

    // ═══════════════════════════════════
    // INJECT PROMPT INTO CHAT
    // ═══════════════════════════════════
    function injectPrompt(text) {
        var scraper = getCurrentScraper();
        if (!scraper) {
            log('Aucun scraper pour ce site: ' + location.hostname);
            return false;
        }

        var textarea = scraper.findTextarea();
        if (!textarea) {
            log('Textarea non trouve');
            return false;
        }

        // Injecter le texte
        if (textarea.contentEditable === 'true') {
            textarea.innerHTML = '';
            textarea.innerText = text;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
            textarea.value = text;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Cliquer envoyer
        var btn = scraper.findSendButton();
        if (btn) {
            btn.click();
            return true;
        }

        // Fallback: simuler Enter
        textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        return true;
    }

    // ═══════════════════════════════════
    // WAIT FOR RESPONSE
    // ═══════════════════════════════════
    function waitForResponse(callback) {
        var scraper = getCurrentScraper();
        if (!scraper) { callback(null); return; }

        var startTime = Date.now();
        var lastLength = 0;
        var stableCount = 0;

        var check = setInterval(function() {
            if (Date.now() - startTime > 120000) {
                clearInterval(check);
                log('Timeout attente reponse');
                callback(null);
                return;
            }

            if (!scraper.isGenerating()) {
                var resp = scraper.findResponse();
                if (resp && resp.length > 10 && resp.length === lastLength) {
                    stableCount++;
                    if (stableCount >= 3) {
                        clearInterval(check);
                        callback(resp);
                        return;
                    }
                } else if (resp) {
                    lastLength = resp.length;
                    stableCount = 0;
                }
            } else {
                lastLength = 0;
                stableCount = 0;
            }
        }, 1000);
    }

    // ═══════════════════════════════════
    // MAIN WORKER LOOP
    // ═══════════════════════════════════
    var idleSince = Date.now();
    var processing = false;

    function workerLoop() {
        if (processing) return;

        apiCall('GET', '/next_prompt', null, function(err, data) {
            if (err) {
                log('Erreur next_prompt: ' + err);
                return;
            }

            if (!data || !data.prompt) {
                // Pas de prompt en attente
                if (Date.now() - idleSince > MAX_IDLE_WAIT) {
                    log('Pas de prompt, ralentissement...');
                }
                return;
            }

            idleSince = Date.now();
            processing = true;

            var promptText = data.retry_prompt || data.prompt;
            log('Prompt recu: ' + promptText.substring(0, 80) + '...');

            // Injecter dans le chat
            var injected = injectPrompt(promptText);
            if (!injected) {
                log('Impossible d\'injecter le prompt');
                apiCall('POST', '/submit_response', {
                    id: data.id,
                    response: 'Erreur: injection echouee'
                }, function() { processing = false; });
                return;
            }

            // Attendre la reponse
            waitForResponse(function(responseText) {
                if (!responseText) {
                    apiCall('POST', '/submit_response', {
                        id: data.id,
                        response: 'Erreur: pas de reponse du LLM'
                    }, function() { processing = false; });
                    return;
                }

                log('Reponse recue: ' + responseText.length + ' chars');

                // Soumettre au serveur
                apiCall('POST', '/submit_response', {
                    id: data.id,
                    response: responseText
                }, function(err, result) {
                    if (result && result.ok) {
                        log('Reponse soumise avec succes');
                    } else {
                        log('Erreur soumission: ' + (result ? result.message : err));
                    }
                    processing = false;
                });
            });
        });
    }

    // Démarrer la boucle
    log('AstarteBam Worker demarre sur ' + location.hostname);
    log('Polling ' + SERVER + ' toutes les ' + POLL_INTERVAL + 'ms');
    setInterval(workerLoop, POLL_INTERVAL);
    workerLoop();

    // Notification de démarrage
    if (typeof GM_notification !== 'undefined') {
        GM_notification({
            title: 'AstarteBam Worker',
            text: 'Actif sur ' + location.hostname,
            timeout: 3000
        });
    }
})();