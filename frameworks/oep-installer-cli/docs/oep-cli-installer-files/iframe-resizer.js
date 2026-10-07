let lastHeight = 0;
const maxHeight = 2000; // Maximum allowed height
const minHeight = 0;    // No hard minimum: let the frame shrink to its content

function resizeIframe() {
    const iframe = document.getElementById('installerFrame');
    if (iframe && iframe.contentWindow) {
        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc) {
                const body = iframeDoc.body;

                // Measure the CONTENT height only. We deliberately avoid
                // html.clientHeight / documentElement.* here: those track the
                // iframe's own viewport height, so including them creates a
                // positive feedback loop (measure >= current height -> grow ->
                // observer fires -> measure taller -> grow again) that made the
                // frame get taller and taller. Measuring the content wrapper
                // instead converges to the real content height.
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

            // Continuously re-fit when the iframe content changes height (e.g. the
            // user selects a module and Next Steps switches between a link and a
            // taller command box). Same-origin (_static) so we can observe it.
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                if (iframeDoc && iframeDoc.body) {
                    if ('ResizeObserver' in window) {
                        const ro = new ResizeObserver(function() {
                            resizeIframe();
                        });
                        ro.observe(iframeDoc.body);
                    }
                    if ('MutationObserver' in window) {
                        const mo = new MutationObserver(function() {
                            resizeIframe();
                        });
                        mo.observe(iframeDoc.body, { childList: true, subtree: true, attributes: true });
                    }
                }
            } catch (e) {
                // Cross-origin or unsupported - fall back to load/resize handlers.
            }
        });
    }
});

// Resize on window resize (but not continuously)
window.addEventListener('resize', function() {
    clearTimeout(window.resizeTimeout);
    window.resizeTimeout = setTimeout(resizeIframe, 250);
});