// ==UserScript==
// @name         VantaEther Sync Agent v1.1 (Stable)
// @namespace    http://localhost/
// @version      2.0
// @description  Advanced stream sniffer with Backoff Retry & Queue System
// @match        *://*/*
// @connect      127.0.0.1
// @grant        GM_xmlhttpRequest
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    const SERVER_URL = "http://127.0.0.1:5005/snipe";
    const sent = new Set();
    const requestQueue = [];
    let isServerOnline = false;
    let retryDelay = 1000; // Start with 1 second
    const MAX_DELAY = 30000; // Cap at 30 seconds

    // UI Notification Helper
    function showNotification(msg, color) {
        const div = document.createElement('div');
        div.style = `position:fixed;top:10px;left:10px;background:${color};color:black;padding:8px;z-index:999999;font-weight:bold;border-radius:4px;font-family:monospace;box-shadow:0 2px 10px rgba(0,0,0,0.5);font-size:12px;pointer-events:none;`;
        div.innerText = msg;
        document.body.appendChild(div);
        setTimeout(() => div.remove(), 3000);
    }

    function showStatus(msg) {
        // Minimal console log to avoid spamming user console
        console.debug(`[VANTA SYSTEM] ${msg}`);
    }

    // --- CONNECTION MANAGER ---

    function flushQueue() {
        if (requestQueue.length === 0) return;
        
        showStatus(`Flushing ${requestQueue.length} queued items...`);
        const batch = [...requestQueue];
        requestQueue.length = 0; // Clear queue
        
        batch.forEach(item => safeSend(item));
    }

    function checkConnection() {
        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:5005/status",
            timeout: 2000,
            onload: function(response) {
                if (response.status === 200) {
                    if (!isServerOnline) {
                        showStatus("Server connection established.");
                        isServerOnline = true;
                        retryDelay = 1000; // Reset backoff
                        flushQueue();
                    }
                }
                setTimeout(checkConnection, 5000); // Heartbeat every 5s
            },
            onerror: function() {
                isServerOnline = false;
                retryDelay = Math.min(retryDelay * 2, MAX_DELAY);
                // showStatus(`Server offline. Retrying in ${retryDelay/1000}s...`);
                setTimeout(checkConnection, retryDelay);
            }
        });
    }

    // Initialize connection check immediately
    checkConnection();

    // --- CAPTURE LOGIC ---

    function safeSend(payload) {
        if (!isServerOnline) {
            // Queue if offline to prevent console errors
            if (!requestQueue.some(i => i.url === payload.url)) {
                requestQueue.push(payload);
            }
            return;
        }

        GM_xmlhttpRequest({
            method: "POST",
            url: SERVER_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify(payload),
            onerror: function(err) {
                isServerOnline = false; // Mark offline immediately on error
                requestQueue.push(payload); // Re-queue
            }
        });
    }

    function capture(url, source) {
        if (!url || typeof url !== 'string') return;
        if (url.startsWith('blob:') || url.startsWith('data:')) return; 
        
        // Filter out non-media static assets
        if (url.match(/\.(jpg|jpeg|png|gif|css|js|woff|woff2|ttf|svg|ico)$/i)) return;
        if (url.includes('google-analytics') || url.includes('doubleclick')) return;

        const isMedia = url.includes('.m3u8') || 
                        url.includes('.mp4') || 
                        url.includes('.mpd') || 
                        url.includes('master.txt') ||
                        url.includes('.vtt') || 
                        url.includes('.srt');

        if (!isMedia) return;
        if (sent.has(url)) return;
        
        sent.add(url);
        
        let type = 'video';
        if (url.includes('.vtt') || url.includes('.srt')) type = 'sub';

        console.log(`[VANTA SNIPER] Captured via ${source}:`, url);
        if (type === 'video') showNotification(`🎥 CAPTURED: ${source}`, '#00ff41');
        else showNotification(`📝 SUBTITLE: ${source}`, '#00ffff');

        const payload = {
            url: url,
            type: type,
            source: source,
            title: document.title,
            page: window.location.href,
            cookies: document.cookie,
            agent: navigator.userAgent,
            referrer: document.referrer
        };

        safeSend(payload);
    }

    // ---- 1. FETCH API TRAP ----
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const [resource, config] = args;
        const url = (resource instanceof Request) ? resource.url : resource;
        capture(url, "FETCH");
        
        try {
            const response = await originalFetch.apply(this, args);
            if (response.url && response.url !== url) capture(response.url, "FETCH_REDIR");
            return response;
        } catch(e) { return originalFetch.apply(this, args); }
    };

    // ---- 2. XHR TRAP ----
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        capture(url, "XHR");
        this.addEventListener('load', function() { 
            if (this.responseURL && this.responseURL !== url) {
                capture(this.responseURL, "XHR_REDIR");
            }
        });
        return originalOpen.apply(this, arguments);
    };

    // ---- 3. MEDIA SRC PROPERTY TRAP ----
    const srcDescriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    if (srcDescriptor) {
        Object.defineProperty(HTMLMediaElement.prototype, 'src', {
            set(v) {
                capture(v, "DOM_SRC");
                return srcDescriptor.set.call(this, v);
            },
            get() { return srcDescriptor.get.call(this); }
        });
    }

    // ---- 4. IFRAME INJECTION TRAP ----
    const originalCreateElement = document.createElement;
    document.createElement = function(tag) {
        const element = originalCreateElement.call(document, tag);
        if (tag.toLowerCase() === 'iframe') {
            element.addEventListener('load', () => {
                try {
                    const w = element.contentWindow;
                    if (w && w.fetch && w.fetch !== window.fetch) {
                        const iframeFetch = w.fetch;
                        w.fetch = async function(...args) {
                            const [res] = args;
                            capture((res instanceof Request) ? res.url : res, "IFRAME_FETCH");
                            return iframeFetch.apply(this, args);
                        };
                    }
                } catch(e) { /* Cross-origin blocked */ }
            });
        }
        return element;
    };

})();