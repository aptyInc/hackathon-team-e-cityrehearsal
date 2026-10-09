// Terascope AI: small helpers shared by the content pages (index.html, decisions.html, data.html). Owner: Frontend.
// window.CR = {API, $, esc, get, when, hhmm, pct, POINTS, pointName, ivText, STAGES, stageName, decisionText, fp, lab, apiProblem, plain}
window.CR = (() => {
  const API = window.CR_API || "http://localhost:8000";
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // Text from the API in plain words: the screens say "real data" (measured) or "simulated", not the data provider's name
  // or the month the saved averages come from. "measured (TomTom live flow)" -> "measured (real data · live)".
  const plain = s => String(s ?? "").replace(/TomTom live( flow)?/g, "real data · live")
    .replace(/TomTom(['’]s)?( (Traffic Stats|Junction Analytics|probe (data|vehicles)|hourly|data))?/g, "real data")
    .replace(/([Tt])ypical July day/g, "$1ypical day").replace(/,? ?July 2026/g, "").replace(/\bJuly\b/g, "typical-day");
  // GET with a timeout. Errors carry .status (the HTTP status; undefined when the API is not reachable) and .detail.
  async function get(path, ms = 10000) {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
    try {
      const r = await fetch(API + path, { signal: ctl.signal });
      if (!r.ok) {
        let d = (await r.text()).trim();
        try { const j = JSON.parse(d); if (j && j.detail) d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { /* plain text */ }
        const err = new Error(`${path}: ${r.status} ${d.slice(0, 160)}`); err.status = r.status; err.detail = d.slice(0, 300); throw err;
      }
      return await r.json();
    } finally { clearTimeout(t); }
  }
  const toDate = t => new Date(typeof t === "number" && t < 1e12 ? t * 1000 : t);   // epoch seconds or ms, or ISO text
  const when = t => { const d = toDate(t); return t != null && t !== "" && !isNaN(d) ? d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }) : ""; };
  const hhmm = t => { const d = toDate(t); return t != null && !isNaN(d) ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }) : ""; };
  const pct = v => `${Math.round(Number(v) * 100)}%`;
  // Corridor points (data/corridor/corridor.json), for plain names where the API sends ids. GET /corridor may replace them.
  const POINTS = { A_lingampally: "Lingampally", j01: "Nallagandla Rd jn", j02: "ISB Rd / DLF jn", j03: "Gachibowli Circle", j04: "Biodiversity jn",
                   j05: "Khajaguda X Roads", j06: "Narne Rd jn Shaikpet", j07: "Tolichowki", j08: "Nanal Nagar jn", j09: "Rethibowli jn",
                   j10: "NMDC / Masab Tank Rd", j11: "Masab Tank", B_lakdikapul: "Lakdikapul" };
  const pointName = id => POINTS[id] || id;
  const KINDS = { flyover: "Flyover", underpass: "Underpass", signal_retime: "Signal timing", widening: "Road widening", one_way: "One-way side road", u_turn: "U-turn change" };
  function ivText(iv) {
    const p = iv.params || {}, bits = [];
    if (p.lanes) bits.push(`${p.lanes} lane${p.lanes > 1 ? "s" : ""}`);
    if (p.add_lanes) bits.push(`+${p.add_lanes} lane${p.add_lanes > 1 ? "s" : ""}`);
    if (p.length_m) bits.push(`${p.length_m} m`);
    if (p.cycle_s) bits.push(`${p.cycle_s} s cycle`);
    const g = p.corridor_green_share ?? p.main_share;
    if (g != null) bits.push(`${Math.round(g * 100)}% green to main road`);
    return `${KINDS[iv.kind] || iv.kind} at ${pointName(iv.junction_id)}${bits.length ? ` (${bits.join(", ")})` : ""}`;
  }
  const STAGES = [["proposed", "Proposed"], ["in_review", "In review"], ["decided", "Decided"]];
  const stageName = s => (STAGES.find(x => x[0] === s) || [s, s || "–"])[1];
  const DECISIONS = { approve: "Approved", reject: "Rejected", revise: "Sent back for revision", defer: "Deferred" };
  const decisionText = d => DECISIONS[String(d || "").toLowerCase()] || String(d || "Decided").replace(/^./, c => c.toUpperCase());
  // A SHA-256 fingerprint: the first 10 characters, the full one on hover (and focus).
  const fp = h => h ? `<code class="fp" tabindex="0" title="SHA-256 ${esc(h)}" data-full="${esc(h)}">${esc(String(h).slice(0, 10))}</code>` : "–";
  // An input label (counted / measured / estimated / assumed / calibrated), from text such as "calibrated: speed cap ...".
  function lab(text) {
    const w = String(text || "").trim().toLowerCase().match(/^(counted|measured|estimated|assumed|calibrated)/);
    return `<span class="lab ${w ? w[1] : "other"}">${esc(w ? w[1] : plain(text) || "–")}</span>`;
  }
  // A plain-language line for a failed GET.
  const apiProblem = (e, what) => e && e.status === 404 ? `${what} ${what.endsWith("s") ? "are" : "is"} not on this server yet.`
    : e && e.status ? `${what}: the API answered ${e.status}${e.detail ? ` (${plain(e.detail).slice(0, 120)})` : ""}.`
    : `${what} need${what.endsWith("s") ? "" : "s"} the API, which is not answering (start it with \`make dev\`).`;
  return { API, $, esc, get, when, hhmm, pct, POINTS, pointName, KINDS, ivText, STAGES, stageName, decisionText, fp, lab, apiProblem, plain };
})();
