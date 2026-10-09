// Terascope AI map pages (corridor.html, ymca.html): keep the page itself from being zoomed by accident and always offer
// a way back. Owner: Frontend.
//   - Trackpad pinch / ctrl+wheel over a panel zooms the map's page in the browser, after which the full-screen panels
//     overflow off-screen. A document-level wheel listener cancels ctrl/meta+wheel the map did not use (MapLibre handles
//     it over the map and cancels it itself); Safari's gesture events are cancelled outside the map. Keyboard Cmd/Ctrl +/-
//     is left alone (accessibility). The pages' viewport meta adds maximum-scale=1 against touch pinch.
//   - A floating "Reset view" pill (and the R key) runs the page's reset: camera back to the overview, orbit/follow/ride
//     stopped, popups closed; here every panel is reopened and scrolled to the top. Esc runs the page's `escape`.
//   - Each side panel gets a collapse/expand chevron, so the map can be cleared and restored.
//   - If the page is zoomed anyway (pinch: visualViewport.scale > 1.05; browser zoom: devicePixelRatio up by > 5% since
//     load), a toast says how to undo it, with a Reset view button.
// Use: <script src="viewguard.js"></script>, then crView.init({reset, escape, panels: [{id, label}], above, right}).
//   reset()   the page's camera reset (required);  escape()  stop follow/ride/orbit (optional)
//   panels    the side panels that get a collapse chevron;  above  selector of a bottom-right panel the pill sits above
//   right     the pill's distance from the right edge (px)
window.crView = (() => {
  const css = `
  #reset-view { position: fixed; z-index: 40; right: var(--reset-right, 12px); bottom: var(--reset-bottom, 36px); height: 36px; padding: 0 16px 0 12px;
    display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; border: 1px solid oklch(1 0 0 / .28); cursor: pointer;
    font: 700 11.5px/1 var(--f, "Montserrat", system-ui, sans-serif); letter-spacing: .04em; text-transform: uppercase; color: var(--tx, #fff);
    background: var(--glass-strong, oklch(0.225 0 0 / .9)); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
    box-shadow: 0 8px 22px -8px oklch(0 0 0 / .7); transition: border-color .15s, background .15s; }
  #reset-view:hover { border-color: var(--tx, #fff); filter: none; }
  #reset-view svg { width: 16px; height: 16px; flex: none; color: var(--t-orange, #f58832); }
  #reset-view kbd { font: 600 10px/1 var(--f, sans-serif); color: var(--tx-3, #a3a3a3); border: 1px solid var(--line-2, #666); border-radius: 4px; padding: 2px 4px; letter-spacing: 0; }
  #reset-view:focus-visible, .pcollapse:focus-visible, #zoom-toast button:focus-visible { outline: 2px solid var(--t-orange, #f58832); outline-offset: 2px; }
  .pcollapse { position: absolute; top: 8px; right: 8px; z-index: 3; width: 26px; height: 26px; padding: 0; border-radius: 999px; display: grid; place-items: center;
    background: oklch(1 0 0 / .06) !important; color: var(--tx-2, #ccc) !important; border: 1px solid var(--line-2, #666) !important; box-shadow: none !important; cursor: pointer; }
  .pcollapse:hover { color: var(--tx, #fff) !important; border-color: var(--tx, #fff) !important; filter: none; }
  .pcollapse svg { width: 14px; height: 14px; transition: transform .15s; }
  .pcollapse .lbl { display: none; }
  .panel.collapsed { width: auto !important; min-width: 0 !important; max-height: none !important; overflow: visible !important; padding: 0 !important; background: none !important;
    border: 0 !important; box-shadow: none !important; -webkit-backdrop-filter: none !important; backdrop-filter: none !important; }
  .panel.collapsed > :not(.pcollapse) { display: none !important; }
  .panel.collapsed > .pcollapse { position: static; width: auto; height: 34px; padding: 0 14px 0 10px; display: inline-flex; gap: 6px; align-items: center;
    font: 700 11px/1 var(--f, sans-serif); letter-spacing: .04em; text-transform: uppercase; color: var(--tx, #fff) !important;
    background: var(--glass-strong, oklch(0.225 0 0 / .9)) !important; -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); box-shadow: 0 8px 22px -8px oklch(0 0 0 / .7) !important; }
  .panel.collapsed > .pcollapse .lbl { display: inline; }
  .panel.collapsed > .pcollapse svg { transform: rotate(180deg); }
  #zoom-toast { position: fixed; z-index: 70; left: 50%; top: calc(var(--nav-h, 0px) + 12px); transform: translateX(-50%); transform-origin: top center;
    display: flex; align-items: center; gap: 12px; max-width: min(560px, calc(100vw - 24px)); box-sizing: border-box; padding: 10px 10px 10px 16px;
    border-radius: 14px; font: 500 13px/1.4 var(--f, sans-serif); color: var(--tx, #fff); background: var(--glass-strong, oklch(0.225 0 0 / .94));
    border: 1px solid var(--chg-line, oklch(0.837 0.164 84 / .45)); box-shadow: 0 16px 40px -12px oklch(0 0 0 / .8); }
  #zoom-toast[hidden] { display: none !important; }
  #zoom-toast b { color: var(--chg, #fcbf26); }
  #zoom-toast button { height: 30px; padding: 0 12px; border-radius: 999px; font: 700 11px/1 var(--f, sans-serif); letter-spacing: .04em; text-transform: uppercase; cursor: pointer; }
  #zoom-toast .zt-reset { color: #fff; background: var(--cta, #e23d27); border: 0; }
  #zoom-toast .zt-x { width: 30px; padding: 0; color: var(--tx-2, #ccc); background: transparent; border: 1px solid var(--line-2, #666); }
  @media (max-width: 820px) {
    #reset-view { left: 12px; right: auto; bottom: 12px; }
    .pcollapse { top: 6px; right: 6px; }
    #reset-view kbd { display: none; }
    body { padding-bottom: 60px; }   /* the end of the last panel scrolls clear of the floating pill */
    .panel.has-pcollapse { position: relative !important; inset: auto !important; }   /* the stacked panels: the chevron stays in its panel */
  }
  @media print { #reset-view, #zoom-toast, .pcollapse { display: none !important; } }`;
  const ICON_RESET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><circle cx="12" cy="12" r="2"/></svg>';
  const ICON_CHEVRON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>';
  const $ = id => document.getElementById(id);
  let opts = null, dpr0 = window.devicePixelRatio || 1, dismissed = false;

  function inMap(t) { return !!(t && t.closest && t.closest("#map")); }
  function typing(t) { return !!(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))); }

  // ---------- 1 · no accidental page zoom ----------
  function guard() {
    // bubbling at the document: MapLibre (on the map's container) has already handled and cancelled the wheel over the map
    document.addEventListener("wheel", e => { if ((e.ctrlKey || e.metaKey) && !e.defaultPrevented) e.preventDefault(); }, { passive: false });
    ["gesturestart", "gesturechange", "gestureend"].forEach(t => document.addEventListener(t, e => { if (!inMap(e.target)) e.preventDefault(); }, { passive: false }));
  }

  // ---------- 2 · reset view ----------
  function panelsReset() {
    (opts.panels || []).forEach(p => setCollapsed(p.id, false));
    document.querySelectorAll(".panel").forEach(el => { el.scrollTop = 0; });
    (opts.scroll || []).forEach(sel => document.querySelectorAll(sel).forEach(el => { el.scrollTop = 0; }));
    window.scrollTo(0, 0);
  }
  function reset() {
    try { opts.reset(); } catch (e) { /* the page's reset must not stop the panels coming back */ }
    panelsReset();
    window.dispatchEvent(new CustomEvent("cr:reset-view"));
  }
  function pill() {
    const b = document.createElement("button");
    b.id = "reset-view"; b.type = "button";
    b.title = "Back to the whole view: camera, panels and playback (key R)";
    b.setAttribute("aria-keyshortcuts", "R");
    b.innerHTML = `${ICON_RESET}<span>Reset view</span><kbd aria-hidden="true">R</kbd>`;
    b.onclick = reset;
    document.body.appendChild(b);
    if (opts.right != null) document.documentElement.style.setProperty("--reset-right", `${opts.right}px`);
    const above = opts.above && document.querySelector(opts.above);
    const place = () => {   // sit above the bottom-right panel when it shows, else above the map attribution
      const r = above && above.offsetParent !== null ? above.getBoundingClientRect() : null;
      const bottom = r && r.height ? Math.max(36, Math.round(window.innerHeight - r.top + 10)) : 36;
      document.documentElement.style.setProperty("--reset-bottom", `${bottom}px`);
    };
    place();
    if (above && window.ResizeObserver) new ResizeObserver(place).observe(above);
    window.addEventListener("resize", place);
    if (above) new MutationObserver(place).observe(document.body, { attributes: true, attributeFilter: ["class"] });   // mode changes show / hide it
    window.addEventListener("cr:place-reset", place);
  }
  function keys() {
    document.addEventListener("keydown", e => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
      if ((e.key === "r" || e.key === "R") && !e.repeat) { e.preventDefault(); reset(); }
      else if (e.key === "Escape" && opts.escape) { try { opts.escape(); } catch (err) { /* nothing to stop */ } }
    });
  }

  // ---------- 3 · collapsible panels ----------
  function setCollapsed(id, on) {
    const el = $(id); if (!el) return;
    const b = el.querySelector(":scope > .pcollapse"); if (!b) return;
    el.classList.toggle("collapsed", on);
    b.setAttribute("aria-expanded", String(!on));
    b.title = on ? `Show ${b.dataset.label}` : `Hide ${b.dataset.label} (clear the map)`;
    b.setAttribute("aria-label", b.title);
    window.dispatchEvent(new Event("cr:place-reset"));
  }
  function collapsers() {
    for (const p of opts.panels || []) {
      const el = $(p.id); if (!el) continue;
      const b = document.createElement("button");
      b.type = "button"; b.className = "pcollapse"; b.dataset.label = p.label || "panel"; el.classList.add("has-pcollapse");
      b.setAttribute("aria-controls", p.id);
      b.innerHTML = `${ICON_CHEVRON}<span class="lbl">${p.label || "panel"}</span>`;
      b.onclick = () => setCollapsed(p.id, !el.classList.contains("collapsed"));
      el.insertBefore(b, el.firstChild);
      setCollapsed(p.id, false);
    }
  }

  // ---------- 4 · the page is zoomed anyway: say how to undo it ----------
  function toast() {
    const t = document.createElement("div");
    t.id = "zoom-toast"; t.hidden = true; t.setAttribute("role", "status");
    const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
    t.innerHTML = `<span>The page is zoomed in: press <b>${mac ? "⌘0" : "Ctrl+0"}</b> (${mac ? "Ctrl+0" : "⌘0 on a Mac"}) to reset.</span>` +
      `<button type="button" class="zt-reset">Reset view</button><button type="button" class="zt-x" aria-label="Dismiss" title="Dismiss">✕</button>`;
    t.querySelector(".zt-reset").onclick = () => { reset(); check(); };
    t.querySelector(".zt-x").onclick = () => { dismissed = true; t.hidden = true; };
    document.body.appendChild(t);
    window.addEventListener("resize", check);
    if (window.visualViewport) { visualViewport.addEventListener("resize", check); visualViewport.addEventListener("scroll", check); }
  }
  function zoomed() {
    const vv = window.visualViewport, pinch = vv ? vv.scale : 1, browser = (window.devicePixelRatio || 1) / dpr0;
    return { pinch, browser, on: pinch > 1.05 || browser > 1.05 };
  }
  function check() {
    const t = $("zoom-toast"); if (!t) return;
    const z = zoomed();
    if (!z.on) { dismissed = false; t.hidden = true; return; }
    t.hidden = dismissed;
    const vv = window.visualViewport;
    if (vv && z.pinch > 1.05) {   // keep it inside what is on screen, at its normal size
      t.style.left = `${vv.offsetLeft + vv.width / 2}px`; t.style.top = `${vv.offsetTop + 10 / z.pinch}px`;
      t.style.transform = `translateX(-50%) scale(${1 / z.pinch})`;
    } else { t.style.left = t.style.top = t.style.transform = ""; }
  }

  function init(o) {
    opts = o || {};
    const st = document.createElement("style"); st.id = "cr-view-style"; st.textContent = css; document.head.appendChild(st);
    guard(); collapsers(); pill(); keys(); toast(); check();
    return api;
  }
  const api = { init, reset, setCollapsed, check, zoomed };
  return api;
})();
