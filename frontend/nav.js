// CityRehearsal: the shared top bar on every page (Home · Corridor · YMCA close-up · Decisions · About the data) and an
// API status pill. Owner: Frontend. Load it as the FIRST element of <body>: <script src="nav.js"></script>
// (optionally data-page="corridor" to name the active page; otherwise the file name decides).
// It publishes the bar's height as the CSS variable --nav-h on <html>; pages offset their map and panels with
// var(--nav-h, 0px), so without this script they still work, just without the bar.
// API status: GET /health ({status, mock}), else GET /config ({mock}); neither answering = offline. Re-checked every 30 s.
// window.crNav = {api, state, onChange(fn)}; a "cr:api" event on document carries {state: "real" | "mock" | "offline"}.
(() => {
  const API = window.CR_API || "http://localhost:8000";
  const PAGES = [
    ["home", "index.html", "Home", "Home"],
    ["corridor", "corridor.html", "Corridor", "Corridor"],
    ["ymca", "ymca.html", "YMCA close-up", "YMCA"],
    ["decisions", "decisions.html", "Decisions", "Decisions"],
    ["data", "data.html", "About the data", "Data"],
  ];
  const STATES = {
    checking: ["Checking API…", "Checking API", "Asking the API whether it is running"],
    real: ["Real simulation", "Real sim", "API running with real SUMO simulations (MOCK_SIM=0)"],
    mock: ["Mock: sample data", "Mock", "API running in mock mode: results are the saved samples, tagged SAMPLE DATA (MOCK_SIM=1)"],
    offline: ["API offline", "Offline", "The API on " + API + " is not answering: start it with `make dev`. Pages fall back to saved data where they can."],
  };
  const me = document.currentScript;
  const file = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  const active = (me && me.dataset.page) || (PAGES.find(p => p[1] === file) || PAGES[0])[0];

  const css = `
  :root { --nav-h: 44px; }
  #cr-nav { position: fixed; top: 0; left: 0; right: 0; z-index: 30; box-sizing: border-box; height: 44px; padding: 0 14px;
    display: flex; align-items: center; gap: 18px; background: #16202a; color: #e9e4da; font: 13px/1.2 Inter, system-ui, sans-serif;
    box-shadow: 0 1px 8px rgba(0,0,0,.25); }
  #cr-nav * { box-sizing: border-box; }
  #cr-nav .crn-top { display: flex; align-items: center; gap: 10px; flex: none; }
  #cr-nav .crn-brand { color: #fff; text-decoration: none; font-weight: 800; font-size: 15px; letter-spacing: .2px; display: flex; align-items: center; gap: 7px; white-space: nowrap; }
  #cr-nav .crn-mark { width: 14px; height: 14px; border-radius: 4px; background: #c4561c; box-shadow: inset -5px -5px 0 #2f6f9f; flex: none; }
  #cr-nav .crn-links { display: flex; align-items: stretch; gap: 2px; height: 100%; flex: 1 1 auto; min-width: 0; }
  #cr-nav .crn-links a { color: #c9c3b8; text-decoration: none; padding: 0 10px; display: flex; align-items: center; border-bottom: 3px solid transparent;
    border-top: 3px solid transparent; white-space: nowrap; }
  #cr-nav .crn-links a:hover { color: #fff; }
  #cr-nav .crn-links a[aria-current="page"] { color: #fff; font-weight: 700; border-bottom-color: #c4561c; }
  #cr-nav .crn-links a:focus-visible, #cr-nav .crn-brand:focus-visible { outline: 2px solid #f0a46b; outline-offset: -2px; }
  #cr-nav .crn-short { display: none; }
  #cr-nav .crn-pill { flex: none; display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
    background: rgba(255,255,255,.1); color: #e9e4da; white-space: nowrap; cursor: default; }
  #cr-nav .crn-pill::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #9aa3ab; }
  #cr-nav .crn-pill[data-state="real"] { background: #1a7f37; color: #fff; } #cr-nav .crn-pill[data-state="real"]::before { background: #b7f5c5; }
  #cr-nav .crn-pill[data-state="mock"] { background: #7b2d8b; color: #fff; } #cr-nav .crn-pill[data-state="mock"]::before { background: #f0c8f8; }
  #cr-nav .crn-pill[data-state="offline"] { background: #b00020; color: #fff; } #cr-nav .crn-pill[data-state="offline"]::before { background: #ffd0d6; }
  @media (max-width: 820px) {
    :root { --nav-h: 70px; }
    #cr-nav { position: absolute; height: auto; flex-wrap: wrap; gap: 0; padding: 0 10px; }
    #cr-nav .crn-top { width: 100%; justify-content: space-between; height: 38px; }
    #cr-nav .crn-links { height: 32px; justify-content: space-between; gap: 0; }
    #cr-nav .crn-links a { padding: 0 6px; }
    #cr-nav .crn-long { display: none; } #cr-nav .crn-short { display: inline; }
  }
  @media print { #cr-nav { display: none !important; } }`;
  const style = document.createElement("style");
  style.id = "cr-nav-style";
  style.textContent = css;
  document.head.appendChild(style);

  const nav = document.createElement("header");
  nav.id = "cr-nav";
  nav.setAttribute("role", "banner");
  const label = s => STATES[s] || STATES.checking;
  nav.innerHTML =
    `<div class="crn-top"><a class="crn-brand" href="index.html" title="CityRehearsal: home"><span class="crn-mark" aria-hidden="true"></span>CityRehearsal</a>` +
    `<span class="crn-pill crn-pill-sm" data-state="checking" role="status" aria-live="polite"></span></div>` +
    `<nav class="crn-links" aria-label="Pages">` +
    PAGES.map(([id, href, long, short]) => `<a href="${href}" data-page="${id}"${id === active ? ' aria-current="page"' : ""}>` +
      `<span class="crn-long">${long}</span><span class="crn-short">${short}</span></a>`).join("") +
    `</nav>`;
  // One pill, placed after the links on wide screens and next to the wordmark on phones (CSS order would split focus order).
  const pill = nav.querySelector(".crn-pill");
  const place = () => {
    const narrow = window.matchMedia("(max-width: 820px)").matches;
    if (narrow && pill.parentElement !== nav.querySelector(".crn-top")) nav.querySelector(".crn-top").appendChild(pill);
    if (!narrow && pill.parentElement !== nav) nav.appendChild(pill);
  };
  const body = document.body;
  if (me && me.parentNode === body) body.insertBefore(nav, me); else body.insertBefore(nav, body.firstChild);
  place();

  const setH = () => document.documentElement.style.setProperty("--nav-h", nav.offsetHeight + "px");
  setH();
  window.addEventListener("resize", () => { place(); setH(); });
  if (window.ResizeObserver) new ResizeObserver(setH).observe(nav);

  const listeners = [];
  const state = { api: API, state: "checking", onChange(fn) { listeners.push(fn); if (this.state !== "checking") fn(this.state); } };
  window.crNav = state;
  function show(s) {
    const [long, short, tip] = label(s);
    pill.dataset.state = s;
    pill.innerHTML = `<span class="crn-long">${long}</span><span class="crn-short">${short}</span>`;
    pill.title = tip;
    if (s === state.state) return;
    state.state = s;
    listeners.forEach(fn => { try { fn(s); } catch (e) { /* a page's listener must not break the bar */ } });
    document.dispatchEvent(new CustomEvent("cr:api", { detail: { state: s } }));
  }
  async function getJson(path) {
    const ctl = window.AbortController ? new AbortController() : null;
    const t = ctl ? setTimeout(() => ctl.abort(), 5000) : null;
    try {
      const r = await fetch(API + path, { cache: "no-store", ...(ctl ? { signal: ctl.signal } : {}) });
      if (!r.ok) throw new Error(String(r.status));
      return await r.json();
    } finally { clearTimeout(t); }
  }
  async function probe() {
    let s = "offline";
    try { const h = await getJson("/health"); s = h && h.mock === false ? "real" : "mock"; }
    catch (e) {
      try { const c = await getJson("/config"); s = c && c.mock === false ? "real" : "mock"; } catch (e2) { s = "offline"; }
    }
    show(s);
  }
  show("checking");
  probe();
  setInterval(probe, window.CR_NAV_POLL_MS || 30000);
})();
