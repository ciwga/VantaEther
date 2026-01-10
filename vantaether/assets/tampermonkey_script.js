// ==UserScript==
// @name         VantaEther Sync Agent v2.1
// @namespace    http://localhost/
// @version      2.1
// @description  Combines Visual Notifications, Iframe Injection, File Sniffing and API/Embed Detection.
// @match        *://*/*
// @connect      127.0.0.1
// @grant        GM_xmlhttpRequest
// @run-at       document-start
// ==/UserScript==

/**
 * @fileoverview VantaEther Sync Agent v2.1
 * This script intercepts network requests (Fetch, XHR) and monitors DOM changes
 * to detect video streams, licenses, and API endpoints, sending them to a local server.
 * * IMPROVEMENTS:
 * - Memory leak protection (Set and Queue caps).
 * - Performance checks.
 */

(function() {
    'use strict';

    /**
     * The endpoint URL for the local analysis server.
     * @constant {string}
     */
    const SERVER_URL = "http://127.0.0.1:5005/snipe";
    
    // --- State Management ---

    /**
     * Set to store processed URLs to prevent duplicate processing.
     * Memory Protection: This set is now periodically pruned.
     * @type {Set<string>}
     */
    const sent = new Set();

    /**
     * Queue to hold payloads when the server is offline.
     * Memory Protection: Limited to last 500 requests to prevent browser crash.
     * @type {Array<Object>}
     */
    const requestQueue = [];

    /**
     * Flag indicating the connectivity status of the local server.
     * @type {boolean}
     */
    let isServerOnline = false;

    // --- Memory Protection Helper ---
    
    /**
     * Prunes the 'sent' set if it becomes too large to prevent memory swelling
     * during long browsing sessions.
     */
    function pruneMemory() {
        if (sent.size > 2000) {
            sent.clear(); // Simple clear is faster/safer than partial removal for unique URLs
            // Optional: sendRemoteLog("Agent memory cleaned", "SYSTEM");
        }
    }

    // --- UI Notification Helper ---

    /**
     * Displays a temporary visual notification on the DOM.
     * * @param {string} msg - The message content to display.
     * @param {string} color - The background color (CSS value) for the notification.
     */
    function showNotification(msg, color) {
        if (!document.body) return;
        
        const div = document.createElement('div');
        div.style.cssText = `
            position: fixed; top: 10px; left: 10px; 
            background: ${color}; color: black; padding: 8px 12px; 
            z-index: 2147483647; font-weight: bold; border-radius: 4px; 
            font-family: monospace; box-shadow: 0 4px 10px rgba(0,0,0,0.5); 
            font-size: 12px; pointer-events: none; border: 1px solid rgba(255,255,255,0.3);
        `;
        div.innerText = msg;
        document.body.appendChild(div);
        
        // Remove notification after 4 seconds
        setTimeout(() => { if (div.parentNode) div.remove(); }, 4000);
    }

    // --- Remote Logger ---

    /**
     * Sends a log message to the server for debugging purposes.
     * * @param {string} msg - The log message.
     * @param {string} [level='INFO'] - The severity level of the log.
     */
    function sendRemoteLog(msg, level = 'INFO') {
        safeSend({
            url: `LOG: ${msg}`,
            type: 'video', 
            source: 'REMOTE_LOG',
            title: level,
            page: window.location.href,
            agent: navigator.userAgent
        });
    }

    // --- Connection Manager ---

    /**
     * Flushes queued requests to the server once connection is re-established.
     */
    function flushQueue() {
        if (requestQueue.length === 0) return;
        
        // Process in batches to avoid network congestion
        const batch = requestQueue.splice(0, requestQueue.length);
        batch.forEach(item => safeSend(item));
    }

    /**
     * Periodically checks the health status of the local server.
     * Updates `isServerOnline` state and handles queue flushing.
     */
    function checkConnection() {
        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:5005/status",
            timeout: 2000,
            onload: function(response) {
                if (response.status === 200) {
                    if (!isServerOnline) {
                        isServerOnline = true;
                        sendRemoteLog("VANTA AGENT ONLINE", "SYSTEM");
                        showNotification("🔌 VANTA AGENT ONLINE", "#00ff41");
                        flushQueue();
                    }
                }
                setTimeout(checkConnection, 5000);
            },
            onerror: function() {
                isServerOnline = false;
                setTimeout(checkConnection, 5000);
            }
        });
    }
    // Initialize connection check
    checkConnection();

    /**
     * Safely sends a payload to the server.
     * If the server is offline, adds the payload to the queue.
     * * @param {Object} payload - The data object to send.
     */
    function safeSend(payload) {
        if (!isServerOnline) {
            // Queue protection: prevent unlimited growth
            if (requestQueue.length < 500) {
                const isDuplicate = requestQueue.some(i => i.url === payload.url);
                if (!isDuplicate) requestQueue.push(payload);
            }
            return;
        }

        GM_xmlhttpRequest({
            method: "POST",
            url: SERVER_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify(payload),
            onerror: function() {
                isServerOnline = false;
                if (requestQueue.length < 500) {
                    requestQueue.push(payload);
                }
            }
        });
    }

    // --- Traffic Analyzer ---

    /**
     * Analyzes intercepted URLs to detect media streams, licenses, or APIs.
     * * @param {string} url - The URL to analyze.
     * @param {string} source - The source of the interception (e.g., 'FETCH', 'XHR').
     */
    function analyze(url, source) {
        if (!url || typeof url !== 'string') return;
        if (url.startsWith('data:') || url.startsWith('blob:')) return;
        // Ignore common static assets
        if (url.match(/\.(png|jpg|jpeg|gif|css|woff|woff2|svg|ico|js|json)$/i)) return;

        // 1. Classic File Extension Detection
        const isMpd = url.includes('.mpd') || url.includes('dash');
        const isHls = url.includes('.m3u8') || url.includes('master.txt');
        const isVideoFile = url.match(/\.(mp4|mkv|webm|ts)$/i);
        const isSub = url.match(/\.(vtt|srt)$/i);
        
        // 2. Advanced API and Embed Detection
        const isLicense = /license|widevine|drm|rights/i.test(url) && !url.includes('.html');
        const isPlayerApi = url.includes('/embed/') || 
                            url.includes('molystream') || 
                            /\/q\/\d+/.test(url) ||
                            url.includes('/player/api');

        // Send debug log for analysis
        sendRemoteLog(`[${source}] ${url.substring(0, 100)}`, 'DEBUG');

        if (!isMpd && !isHls && !isLicense && !isVideoFile && !isPlayerApi && !isSub) return;
        
        if (sent.has(url)) return;
        sent.add(url);
        
        // Trigger memory cleanup
        pruneMemory();

        // Determine Type and Notification Color
        let type = 'video';
        let notifColor = '#00ff41'; // Green

        if (isLicense) { type = 'license'; notifColor = '#ff9900'; }
        else if (isMpd) { type = 'manifest_dash'; notifColor = '#ff00ff'; } // Magenta
        else if (isSub) { type = 'sub'; notifColor = '#00ffff'; } // Cyan
        else if (isPlayerApi) { type = 'stream_api'; notifColor = '#ffff00'; } // Yellow

        // Display Notification and Log Success
        showNotification(`⚡ ${type.toUpperCase()}: ${source}`, notifColor);
        sendRemoteLog(`>>> CAPTURED: ${type} - ${url}`, 'SUCCESS');

        const payload = {
            url: url,
            type: type,
            source: source,
            title: document.title,
            page: window.location.href,
            agent: navigator.userAgent
        };
        safeSend(payload);
    }

    // --- Hooks / Interceptors ---
    
    // 1. Fetch API Interceptor
    const originalFetch = window.fetch;
    /**
     * Overrides window.fetch to capture network requests.
     * @param {...*} args - Fetch arguments.
     * @returns {Promise<Response>} The original fetch response.
     */
    window.fetch = function(...args) {
        const [resource] = args;
        const url = (resource instanceof Request) ? resource.url : resource;
        analyze(url, "FETCH");
        return originalFetch.apply(this, args);
    };

    // 2. XMLHttpRequest Interceptor
    const originalOpen = XMLHttpRequest.prototype.open;
    /**
     * Overrides XMLHttpRequest.open to capture XHR requests and redirects.
     * @param {string} method - The HTTP method.
     * @param {string} url - The request URL.
     */
    XMLHttpRequest.prototype.open = function(method, url) {
        analyze(url, "XHR");
        this.addEventListener('readystatechange', function() {
            // Check for redirects on request completion
            if (this.readyState === 4 && this.responseURL && this.responseURL !== url) {
                analyze(this.responseURL, "XHR_REDIR");
            }
        });
        return originalOpen.apply(this, arguments);
    };

    // 3. EME (DRM) Interceptor
    if (navigator.requestMediaKeySystemAccess) {
        const origEME = navigator.requestMediaKeySystemAccess;
        /**
         * Overrides requestMediaKeySystemAccess to detect DRM initialization.
         * @param {string} keySystem - The key system being requested.
         * @param {Object[]} config - The configuration options.
         * @returns {Promise<MediaKeySystemAccess>}
         */
        navigator.requestMediaKeySystemAccess = function(keySystem, config) {
            sendRemoteLog(`DRM INIT: ${keySystem}`, 'DRM_ALERT');
            showNotification(`🔒 DRM DETECTED: ${keySystem}`, '#ff0000');
            safeSend({
                url: "DRM_SIGNAL",
                type: "license",
                source: "EME_API",
                title: keySystem
            });
            return origEME.apply(this, arguments);
        };
    }

    // 4. Iframe Injection and Monitoring
    const originalCreateElement = document.createElement;
    /**
     * Overrides document.createElement to hook into newly created iframes.
     * @param {string} tag - The tag name of the element to create.
     * @returns {HTMLElement} The created element.
     */
    document.createElement = function(tag) {
        const element = originalCreateElement.call(document, tag);
        if (tag.toLowerCase() === 'iframe') {
            element.addEventListener('load', () => {
                try {
                    const w = element.contentWindow;
                    if (w && w.fetch && w.fetch !== window.fetch) {
                        const iframeFetch = w.fetch;
                        // Hook fetch inside the iframe context
                        w.fetch = async function(...args) {
                            const [res] = args;
                            analyze((res instanceof Request) ? res.url : res, "IFRAME_FETCH");
                            return iframeFetch.apply(this, args);
                        };
                    }
                } catch(e) { 
                    // Cross-origin restrictions may block access to contentWindow
                }
            });
        }
        return element;
    };

})();