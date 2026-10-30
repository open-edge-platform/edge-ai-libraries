// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

let lastHeight = 0;
const maxHeight = 2000; // Maximum allowed height
const minHeight = 0;

function resizeIframe() {
    const iframe = document.getElementById('installerFrame');
    if (iframe && iframe.contentWindow) {
        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc) {
                const body = iframeDoc.body;
                // Measuring the iframe viewport creates a feedback loop that
                // prevents it shrinking when content becomes shorter.
                const content = iframeDoc.querySelector('main.app-wrap');
                let height = content
                    ? content.offsetTop + content.scrollHeight
                    : Math.max(body.scrollHeight, body.offsetHeight);
                
                // Apply constraints
                height = Math.max(minHeight, Math.min(maxHeight, height));
                
                // Only update if height has changed significantly
                if (Math.abs(height - lastHeight) > 10) {
                    iframe.style.height = (height + 20) + 'px';
                    lastHeight = height;
                }
            }
        } catch (e) {
            // Cross-origin restrictions - use fixed height
            console.log('Using fallback fixed height due to cross-origin restrictions');
            if (iframe.style.height === '' || iframe.style.height === '600px') {
                iframe.style.height = '800px';
            }
        }
    }
}

// Resize when iframe loads
document.addEventListener('DOMContentLoaded', function() {
    const iframe = document.getElementById('installerFrame');
    if (iframe) {
        iframe.addEventListener('load', function() {
            setTimeout(resizeIframe, 500);
            // Only resize once more after a delay to handle late-loading content
            setTimeout(resizeIframe, 2000);

            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                if (iframeDoc && iframeDoc.body) {
                    if ('ResizeObserver' in window) {
                        const observer = new ResizeObserver(resizeIframe);
                        observer.observe(iframeDoc.body);
                    }
                    if ('MutationObserver' in window) {
                        const observer = new MutationObserver(resizeIframe);
                        observer.observe(iframeDoc.body, { childList: true, subtree: true, attributes: true });
                    }
                }
            } catch (error) {
                console.warn('Cannot observe iframe content; using load and window resize handlers:', error);
            }
        });
    }
});

// Resize on window resize (but not continuously)
window.addEventListener('resize', function() {
    clearTimeout(window.resizeTimeout);
    window.resizeTimeout = setTimeout(resizeIframe, 250);
});