// ==UserScript==
// @name         VantaEther Sync Agent v2.2.0
// @namespace    {{SERVER_URL}}/
// @version      2.2.0
// @description  Combines Visual Notifications, Iframe Injection, File Sniffing and API/Embed Detection.
// @match        *://*/*
// @connect      {{SERVER_HOST}}
// @grant        GM_xmlhttpRequest
// @run-at       document-start
// ==/UserScript==

/**
 * @fileoverview VantaEther Sync Agent v2.2.0
 * This script intercepts network requests (Fetch, XHR) and monitors DOM changes
 * to detect video streams, licenses, and API endpoints, sending them to a local server.
 * * IMPROVEMENTS:
 * - Memory leak protection (Set and Queue caps).
 * - Performance checks.
 * - Content-Type Sniffing for obfuscated streams.
 */

(function() {
    'use strict';

    /**
     * The endpoint URL for the local analysis server.
     * Dynamically injected by VantaEther template engine.
     * @constant {string}
     */
    const SERVER_URL = "{{SERVER_URL}}/snipe";
    
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
            url: "{{SERVER_URL}}/status",
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
     * @param {string|null} [contentType=null] - The HTTP Content-Type header if available.
     */
    function analyze(url, source, contentType = null) {
        if (!url || typeof url !== 'string') return;
        if (url.startsWith('data:') || url.startsWith('blob:')) return;
        // Ignore common static assets unless we have a specific content type telling us otherwise
        if (!contentType && url.match(/\.(png|jpg|jpeg|gif|css|woff|woff2|svg|ico|js|json)$/i)) return;

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
                            url.includes('/api/video/') ||
                            url.includes('/player/api');
        
        // 3. Header-Based Detection (For obfuscated URLs)
        let isHeaderHls = false;
        let isHeaderDash = false;
        
        if (contentType) {
            const ct = contentType.toLowerCase();
            isHeaderHls = ct.includes('application/vnd.apple.mpegurl') || 
                          ct.includes('application/x-mpegurl') ||
                          ct.includes('video/mp2t');
            
            isHeaderDash = ct.includes('application/dash+xml');
        }

        // Send debug log for analysis
        sendRemoteLog(`[${source}] ${url.substring(0, 100)}`, 'DEBUG');

        if (!isMpd && !isHls && !isLicense && !isVideoFile && !isPlayerApi && !isSub && !isHeaderHls && !isHeaderDash) return;
        
        if (sent.has(url)) return;
        sent.add(url);
        
        // Trigger memory cleanup
        pruneMemory();

        // Determine Type and Notification Color
        let type = 'video';
        let notifColor = '#00ff41'; // Green

        if (isLicense) { type = 'license'; notifColor = '#ff9900'; } // Orange
        else if (isMpd || isHeaderDash) { type = 'manifest_dash'; notifColor = '#ff00ff'; } // Magenta
        else if (isSub) { type = 'sub'; notifColor = '#00ffff'; } // Cyan
        else if (isPlayerApi) { type = 'stream_api'; notifColor = '#ffff00'; } // Yellow
        else if (isHeaderHls) { type = 'manifest_hls'; notifColor = '#00ff41'; } // Green

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
     * inspects BOTH the request URL and the response Headers.
     * @param {...*} args - Fetch arguments.
     * @returns {Promise<Response>} The original fetch response.
     */
    window.fetch = async function(...args) {
        const [resource] = args;
        const url = (resource instanceof Request) ? resource.url : resource;
        
        // Preliminary check based on URL
        analyze(url, "FETCH");

        try {
            const response = await originalFetch.apply(this, args);
            // Deep check based on Headers (for obfuscated streams)
            const type = response.headers.get('content-type');
            if (type) {
                analyze(response.url, "FETCH_HEADER", type);
            }
            return response;
        } catch (e) {
            // If fetch fails, we just propagate the error, 
            // initial analyze call covered the request.
            throw e;
        }
    };

    // 2. XMLHttpRequest Interceptor
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;

    /**
     * Overrides XMLHttpRequest.open to capture XHR requests and redirects.
     * @param {string} method - The HTTP method.
     * @param {string} url - The request URL.
     */
    XMLHttpRequest.prototype.open = function(method, url) {
        this._vantaUrl = url; // Store URL for later use
        analyze(url, "XHR");
        return originalOpen.apply(this, arguments);
    };

    /**
     * Overrides XMLHttpRequest.send to attach listeners for header inspection.
     */
    XMLHttpRequest.prototype.send = function() {
        this.addEventListener('readystatechange', function() {
            // Check headers when headers are received (HEADERS_RECEIVED = 2) or DONE (4)
            if (this.readyState === 4) {
                const responseURL = this.responseURL || this._vantaUrl;
                const type = this.getResponseHeader("Content-Type");
                if (type && responseURL) {
                     analyze(responseURL, "XHR_HEADER", type);
                }
            }
        });
        return originalSend.apply(this, arguments);
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
                            const url = (res instanceof Request) ? res.url : res;
                            
                            analyze(url, "IFRAME_FETCH");

                            try {
                                const response = await iframeFetch.apply(this, args);
                                const type = response.headers.get('content-type');
                                if (type) {
                                    analyze(response.url, "IFRAME_HEADER", type);
                                }
                                return response;
                            } catch (e) { throw e; }
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