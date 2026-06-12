// ── Mermaid diagram rendering ──
//
// Ticket bodies can carry ```mermaid fences, which the server renders as
// `<pre class="mermaid">` with the diagram source HTML-escaped (see
// server/markdown.py — the html:False XSS control extends to this path).
// The ~3MB vendored bundle is only fetched the first time a page (or a
// fresh SSE swap) actually contains a diagram.

let loading = null;

function loadMermaid() {
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/static/js/vendor/mermaid.min.js';
    s.onload = () => {
      const theme = document.documentElement.getAttribute('data-theme') === 'dark'
        ? 'dark' : 'default';
      // securityLevel 'strict' keeps click handlers and javascript: links
      // out of generated SVG — diagram source is agent/user-supplied.
      window.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme });
      resolve(window.mermaid);
    };
    s.onerror = (err) => { loading = null; reject(err); };
    document.head.appendChild(s);
  });
  return loading;
}

// Render any not-yet-processed diagrams under `root`. Safe to call again
// after a DOM swap: mermaid marks rendered nodes with data-processed.
export async function renderMermaid(root = document) {
  const nodes = [...root.querySelectorAll('pre.mermaid:not([data-processed])')];
  if (!nodes.length) return;
  try {
    const mermaid = await loadMermaid();
    await mermaid.run({ nodes });
  } catch {
    // Parse errors leave mermaid's own error SVG (or the raw source) in
    // place; never let a bad diagram break the page or an SSE swap.
  }
}

export function initMermaid() {
  renderMermaid();
}
