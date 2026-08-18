"""The module-opening splash — deliberately client-side.

⚠️ READ THIS BEFORE REPLACING IT WITH SOMETHING THAT LOOKS TIDIER IN PYTHON.

Three server-side versions were built and all three failed, for one reason:
Streamlit only swaps the visible page when a script run CONCLUDES. Going from
the landing page to a module changes the whole script path, and for the entire
duration of that run the browser keeps showing the page it already had.

  · a placeholder filled then cleared inside one run  — never painted at all
  · st.rerun() to force a splash-only frame           — the abandoned run left
                                                        the landing page's own
                                                        elements behind
  · st.spinner() around the load                      — DOES flush mid-run, but
                                                        only ~480 ms in, and it
                                                        paints OVER the still
                                                        visible landing page,
                                                        which then survives into
                                                        the half-drawn module

So the overlay is put up by the browser, on the click itself, with no server
round trip in between — which is the only way "the moment I click" can
actually mean that. Python's only job is to take it down again, once the
module has finished rendering.

Same-origin: a components.html iframe can reach window.parent.document, and
the overlay is appended to the parent's <body>, outside Streamlit's managed
element tree — so Streamlit will neither prune it early nor fight over it.
"""
from __future__ import annotations

import streamlit.components.v1 as components

_OVERLAY_ID = "hip-splash"

# Armed on the landing page. Attaches ONE capturing click listener to the
# parent document; the listener puts the overlay up before Streamlit has even
# been told a button was pressed.
ARM_JS = """
<script>
(function () {
  const win = window.parent;
  const doc = win.document;

  // ⚠️ The listener is RE-ATTACHED on every landing render, and the previous
  // one is explicitly removed first. It cannot simply be attached once:
  // although it is registered on the PARENT document, the handler function
  // itself belongs to this iframe's JS realm, and Streamlit destroys this
  // iframe the moment you navigate into a module. Coming back to the landing
  // page, the old listener is a corpse — registered but dead — so an
  // "already armed, skip" guard meant the splash worked exactly once per
  // session. Removing by the handle parked on the parent window is what makes
  // the swap clean rather than stacking a new listener each visit.
  if (win.__hipSplashHandler) {
    doc.removeEventListener('click', win.__hipSplashHandler, true);
  }

  // The stylesheet has no such problem — it is inert markup, not a closure —
  // so it is injected once and left alone.
  if (!doc.getElementById('hip-splash-style')) {
  const css = doc.createElement('style');
  css.id = 'hip-splash-style';
  css.textContent = `
    #%(ID)s{position:fixed;inset:0;z-index:2147483647;
      display:flex;align-items:center;justify-content:center;
      background:
        radial-gradient(1100px 520px at 12%% -12%%, rgba(46,230,214,.10), transparent 62%%),
        radial-gradient(900px 480px at 88%% -6%%, rgba(77,141,255,.10), transparent 60%%),
        #0b0f14;
      font-family:'Inter',system-ui,sans-serif;}
    /* ⚠️ NO fade-in. A 120 ms ease-out was tried and it is precisely the
       complaint this overlay exists to answer: during the fade the landing
       tiles are still legible through it, which reads as "the old page is
       hanging around". Opaque on the very first frame instead. */
    #%(ID)s .hip-card{display:flex;flex-direction:column;align-items:center;
      gap:15px;}
    #%(ID)s .hip-ring{width:54px;height:54px;border-radius:50%%;
      border:3px solid rgba(255,255,255,.10);
      border-top-color:var(--hipc,#2ee6d6);
      animation:hipspin .8s linear infinite;}
    @keyframes hipspin{to{transform:rotate(360deg)}}
    #%(ID)s .hip-txt{font-family:'Sora','Inter',sans-serif;font-size:1.05rem;
      font-weight:700;color:#e5edf5;letter-spacing:-.01em;}
    #%(ID)s .hip-sub{font-size:.8rem;color:#8fa3ba;margin-top:-9px;}
  `;
  doc.head.appendChild(css);
  }

  function overlay(name, sub, accent) {
    if (doc.getElementById('%(ID)s')) return;
    const ov = doc.createElement('div');
    ov.id = '%(ID)s';
    if (accent) ov.style.setProperty('--hipc', accent);
    const safe = (s) => (s || '').replace(/[<>&]/g, '');
    ov.innerHTML =
      '<div class="hip-card"><div class="hip-ring"></div>' +
      '<div class="hip-txt">Opening ' + safe(name) + '…</div>' +
      (sub ? '<div class="hip-sub">' + safe(sub) + '</div>' : '') +
      '</div>';
    doc.body.appendChild(ov);
    // Safety net so a stuck overlay can never trap the visitor. Scheduled on
    // the PARENT window, not this iframe — this iframe is torn down during
    // the very navigation being covered, and a timer belonging to it would
    // die with it.
    win.setTimeout(() => { const e = doc.getElementById('%(ID)s');
                           if (e) e.remove(); }, 20000);
  }

  const handler = function (ev) {
    const btn = ev.target.closest && ev.target.closest('button');
    if (!btn || btn.disabled) return;
    const wrap = btn.closest('[class*="st-key-tile_"], '
                           + '[class*="st-key-backbone_strip"]');
    if (!wrap) return;                       // not a module-opening button
    if (wrap.className.indexOf('tile_ghost') !== -1) return;   // "More modules"
    const tile = wrap.querySelector('.tile');
    const accent = tile
      ? getComputedStyle(tile).getPropertyValue('--tile').trim() : '';
    const nameEl = wrap.querySelector('.tile-name, .backbone-strip-name');
    const subEl = wrap.querySelector('.tile-tag, .backbone-strip-tag');
    overlay(nameEl ? nameEl.textContent : 'module',
            subEl ? subEl.textContent : '', accent);
  };
  win.__hipSplashHandler = handler;
  doc.addEventListener('click', handler, true);
})();
</script>
""" % {"ID": _OVERLAY_ID}

# Rendered once a module has finished drawing. Removing the node is all that
# is needed — it was never part of Streamlit's tree.
DISMISS_JS = """
<script>
(function () {
  const doc = window.parent.document;
  const go = () => { const e = doc.getElementById('%(ID)s'); if (e) e.remove(); };
  // One frame of grace so the module's own first paint lands underneath the
  // overlay rather than appearing to flash in behind it.
  requestAnimationFrame(() => requestAnimationFrame(go));
  setTimeout(go, 350);
})();
</script>
""" % {"ID": _OVERLAY_ID}


def arm() -> None:
    """Call on the landing page, after the module tiles exist."""
    components.html(ARM_JS, height=0)


def dismiss() -> None:
    """Call at the very end of a module's render."""
    components.html(DISMISS_JS, height=0)
