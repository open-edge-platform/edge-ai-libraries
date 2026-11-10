// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const minHeight = 0;    // No hard minimum: let the frame shrink to its content

function initializeIframe(iframe) {
    let lastHeight = 0;
    let resizeObserver;
    let mutationObserver;

    function resizeIframe() {
        if (iframe.contentWindow) {
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                if (iframeDoc?.body) {
                    // Measure content, not the iframe viewport, to avoid a resize feedback loop.
                    const content = iframeDoc.querySelector('main.app-wrap');
                    let height = content
                        ? content.offsetTop + content.scrollHeight
                        : Math.max(iframeDoc.body.scrollHeight, iframeDoc.body.offsetHeight);
                    height = Math.max(minHeight, height);

                    if (Math.abs(height - lastHeight) > 10) {
                        iframe.style.height = (height + 20) + 'px';
                        lastHeight = height;
                    }
                }
            } catch (e) {
                console.log('Using fallback fixed height due to cross-origin restrictions');
                if (iframe.style.height === '' || iframe.style.height === '600px') {
                    iframe.style.height = '800px';
                }
            }
        }
    }

    function observeContent() {
        resizeObserver?.disconnect();
        mutationObserver?.disconnect();
        resizeIframe();
        setTimeout(resizeIframe, 500);
        setTimeout(resizeIframe, 2000);

        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc?.body) {
                if ('ResizeObserver' in window) {
                    resizeObserver = new ResizeObserver(resizeIframe);
                    resizeObserver.observe(iframeDoc.body);
                }
                if ('MutationObserver' in window) {
                    mutationObserver = new MutationObserver(resizeIframe);
                    mutationObserver.observe(iframeDoc.body, { childList: true, subtree: true, attributes: true });
                }
            }
        } catch (e) {
            // Cross-origin frames use the fixed-height fallback in resizeIframe.
        }
    }

    iframe.addEventListener('load', observeContent);
    const source = new URL(iframe.src, document.baseURI);
    const fixedProfile = source.searchParams.get('ENABLE_ONE_PROFILE') === 'true'
        && source.searchParams.has('PROFILE');
    const params = new URLSearchParams(window.location.search);
    for (const key of ['OP_SYSTEM', 'PROFILE', 'MODULE', 'OPTIONS', 'ENABLE_ONE_PROFILE']) {
        if (fixedProfile && (key === 'PROFILE' || key === 'ENABLE_ONE_PROFILE')) continue;
        if (params.has(key)) {
            source.searchParams.set(key, params.get(key));
        }
    }
    if (source.href !== iframe.src) {
        iframe.src = source.href;
    }
    observeContent();
    return resizeIframe;
}

function initializeInstallerFrames() {
    const resizeFrames = Array.from(
        document.querySelectorAll('iframe.installer-frame, iframe#installerFrame'),
        initializeIframe
    );
    let resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => resizeFrames.forEach((resize) => resize()), 250);
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeInstallerFrames);
} else {
    initializeInstallerFrames();
}
