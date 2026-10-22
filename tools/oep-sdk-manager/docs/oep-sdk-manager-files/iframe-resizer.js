let lastHeight = 0;
const maxHeight = 1200; // Maximum allowed height
const minHeight = 400;  // Minimum height

function resizeIframe() {
    const iframe = document.getElementById('installerFrame');
    if (iframe && iframe.contentWindow) {
        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc) {
                const body = iframeDoc.body;
                const html = iframeDoc.documentElement;
                let height = Math.max(
                    body.scrollHeight,
                    body.offsetHeight,
                    html.clientHeight,
                    html.scrollHeight,
                    html.offsetHeight
                );
                
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
        });
    }
});

// Resize on window resize (but not continuously)
window.addEventListener('resize', function() {
    clearTimeout(window.resizeTimeout);
    window.resizeTimeout = setTimeout(resizeIframe, 250);
});