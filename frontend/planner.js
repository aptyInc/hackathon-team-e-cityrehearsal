// Terascope AI corridor page: "Ask Terascope AI" (agent chat) and "4 · Decision" (review and decision records).
// Owner: Frontend. Loaded by corridor.html after its main script; uses its globals (API, get, post, esc, base, changed,
// interventions, renderJourney, play, ...). Backend endpoints (all optional: a 404 hides the feature with a short note):
//   POST /agent/chat?async=1 {session_id?, message} -> {session_id, turn_id}   (or the finished turn, if async is not supported)
//   GET  /agent/turns/{turn_id} -> {status: running|done|failed, steps, reply?, run_ids?, brief_id?, error?}
//   GET  /briefs/{brief_id} -> {brief_id, markdown, run_ids, fingerprints, created_at}
//   GET  /runs/{run_id} -> stored C5 result
//   POST /corridor/cases {title, run_ids, brief_id?}; POST /corridor/cases/{id}/review {reviewer, volume_scale?, note?};
//   POST /corridor/cases/{id}/decide {decider, decision, reason}; GET /corridor/cases/{id}; GET /corridor/cases
window.planner = (() => {
  const POLL_MS = window.AGENT_POLL_MS || 1000;
  const TURN_LIMIT_MS = 15 * 60 * 1000;
  const SUGGESTIONS = ["Where does the trip lose the most time?",
                       "Should we build a flyover at ISB Rd / DLF? Try a cheaper option first.",
                       "What would rain do to the trip?"];
  const STAGES = [["proposed", "Proposed"], ["in_review", "In review"], ["decided", "Decided"]];
  const DONE = { approve: "Approved", reject: "Rejected", revise: "Sent back for revision" };
  const decisionText = d => DONE[String(d || "").toLowerCase()] || String(d || "Decided").replace(/^./, ch => ch.toUpperCase());
  const store = { get: k => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } },
                  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } } };
  const unavailable = e => e && [404, 405, 501].includes(e.status);
  const minsOf = s => Math.round(s / 60);
  const pct = v => `${Math.round(Number(v) * 100)}%`;
  const when = t => { const d = new Date(t); return t && !isNaN(d) ? d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }) : ""; };
  const fp = h => h ? `<code class="fp" title="SHA-256 ${esc(h)}">${esc(String(h).slice(0, 10))}</code>` : "";
  // Text from the API in plain words: "real data" (measured) or simulated, not the data provider's name or the month of the averages.
  const plain = s => String(s ?? "").replace(/TomTom live( flow)?/g, "real data · live")
    .replace(/TomTom(['’]s)?( (Traffic Stats|Junction Analytics|probe (data|vehicles)|hourly|data))?/g, "real data")
    .replace(/([Tt])ypical July day/g, "$1ypical day").replace(/,? ?July 2026/g, "").replace(/\bJuly\b/g, "typical-day");

  // ---------- safe markdown: shared with decisions.html (md.js, loaded before this file) ----------
  const { md } = window.crMarkdown;

  // ---------- runs: fetch a stored C5 result and show it as the "with changes" (or today's) result ----------
  const runCache = {};
  async function fetchRun(id) {
    if (runCache[id]) return runCache[id];
    let r = await get(`/runs/${encodeURIComponent(id)}`);
    r = r && r.result && r.result.journey ? r.result : r;   // tolerate a wrapper {run_id, status, result}
    if (!r || !r.journey || !Array.isArray(r.journey.legs)) throw new Error("not a corridor result");
    return (runCache[id] = r);
  }
  const vol = r => Number(r?.inputs?.volume_scale ?? 1);
  const cond = r => JSON.stringify([vol(r), runParams(r)]);   // same traffic, hour and weather: runs that can be compared
  async function loadRun(id, siblings = []) {
    const r = JSON.parse(JSON.stringify(await fetchRun(id)));
    const ivs = r.interventions || [];
    let baseNote = "";
    if (!ivs.length) { base = r; if (changed && cond(changed) !== cond(r)) changed = null; }
    else {
      interventions = JSON.parse(JSON.stringify(ivs)); sortIvs();
      setMergeNote(ivs.some(coversBoth) ? MERGE_NOTE : "");
      r._ivs = ivKey(interventions); changed = r;
      if (!base || cond(base) !== cond(r) || base._fallback) {   // a baseline to compare with: one the agent ran at the same traffic (hour, weather), else simulate today
        let b = null;
        for (const s of siblings.filter(s => s !== id)) {
          try { const x = await fetchRun(s); if (!(x.interventions || []).length && cond(x) === cond(r)) { b = JSON.parse(JSON.stringify(x)); break; } } catch (e) { /* skip */ }
        }
        if (!b && vol(r) === 1) {   // today's roads at the run's own hour and weather (the page's choice when they match, with its sample fallback)
          const own = runParams(r), same = JSON.stringify(own) === JSON.stringify(simParams());
          try { const x = same ? await corridorRun([]) : await post("/corridor/runs", { interventions: [], volume_scale: 1.0, ...own }); if (!x._fallback) b = x; } catch (e) { /* compare without a baseline */ }
        }
        if (b) base = b; else { base = null; baseNote = " (no run of today's roads at the same traffic to compare with)"; }
      }
    }
    showSource(); ivsChanged(); renderJunctions(); renderWatch(); render();
    const what = ivs.length ? `with ${ivs.map(iv => `${ivText(iv).toLowerCase()} at ${short(point(iv.junction_id)?.name || iv.junction_id)}`).join("; ")}` : "today's roads";
    $("status").textContent = `Showing the assistant's run ${r.run_id}: ${what}${runHour(r) != null || runWeather(r) ? ` (${simDay(r).replace(/^Simulated /, "")})` : ""}`;
    $("run-note").innerHTML = `Loaded from the assistant: run <code>${esc(r.run_id)}</code>${vol(r) !== 1 ? ` at <b>${pct(vol(r))}</b> traffic` : ""}${esc(baseNote)} · ` +
      `traffic input: <b>${esc(plain(r.inputs?.label) || "–")}</b> (${esc(plain(r.inputs?.counts_source) || "–")})` + wxResultLine(r);
    play(r);
    return r;
  }

  // ---------- Ask Terascope AI ----------
  let session = null, turnBusy = false, chatOff = false, lastBrief = null;
  function openChat(on) {
    document.body.classList.toggle("chat-open", on);
    $("chat").hidden = !on;
    $("ask-open").setAttribute("aria-expanded", String(on));
    $("ask-open").textContent = on ? "Close assistant" : "Ask Terascope AI";
    if (on) { if (narrow()) $("chat").scrollIntoView({ behavior: "smooth", block: "start" }); if (!chatOff) $("chat-in").focus({ preventScroll: true }); }
  }
  function toolName(t) {
    const n = String(t || "step").replace(/^(corridor_|run_)/, "").replace(/_/g, " ");
    return { "simulate corridor": "simulating the corridor", "corridor run": "simulating the corridor", "write brief": "writing the decision brief",
             "get live junctions": "reading live junction data", "compare runs": "comparing runs" }[n] || n;
  }
  function stepInput(s) {   // the tool input, as an object (a JSON string is parsed)
    if (typeof s.input === "string") { try { return JSON.parse(s.input) || {}; } catch (e) { return {}; } }
    return s.input && typeof s.input === "object" ? s.input : {};
  }
  function stepText(s) {
    const inp = stepInput(s);
    if (Array.isArray(inp.interventions)) {
      const v = inp.volume_scale && Number(inp.volume_scale) !== 1 ? ` at ${pct(inp.volume_scale)} traffic` : "";
      return (inp.interventions.length ? inp.interventions.map(iv => `${ivText(iv).toLowerCase()} at ${short(point(iv.junction_id)?.name || iv.junction_id)}`).join("; ") : "today's roads") + v;
    }
    return toolName(s.tool);
  }
  // A step is running when it says so, or (no status given) when it is the last one of a running turn and has no result yet.
  const isRunning = (s, k, steps, t) => t.status === "running" && (s.status === "running" || (!s.status && k === steps.length - 1 && !s.summary && !s.run_id));
  const isFailed = (s, t) => s.status === "failed" || !!s.error || (t.status !== "running" && s.status === "running");   // a step left running by a finished turn did not finish
  function stepsHtml(steps, t) {
    return steps.map((s, k) => {
      if (isRunning(s, k, steps, t)) {
        const t0 = t.seen[k] || (t.seen[k] = Date.now());
        return `<li class="run"><span class="spin"></span>Running: ${esc(stepText(s))}… <b class="el">${clock((Date.now() - t0) / 1000)}</b></li>`;
      }
      const bad = isFailed(s, t);
      return `<li class="${bad ? "bad" : ""}"><span class="ck">${bad ? "✕" : "✓"}</span>${esc(plain(s.summary || stepText(s)))}${bad && s.error ? `: ${esc(plain(s.error))}` : ""}` +
        `${s.run_id ? ` <small class="muted">· run ${esc(s.run_id)}</small>` : ""}</li>`;
    }).join("");
  }
  function runIdsOf(t) {
    const ids = [...(t.steps || []).map(s => s && s.run_id), ...(t.run_ids || [])].filter(x => typeof x === "string" && x);
    return [...new Set(ids)];
  }
  function runLabel(t, id) {
    const s = (t.steps || []).find(x => x && x.run_id === id);
    return s ? (Array.isArray(stepInput(s).interventions) ? stepText(s) : plain(s.summary) || id) : id;
  }
  function drawTurn(t) {
    const el = t.el, steps = (t.steps || []).filter(s => s && typeof s === "object"), log = $("chat-log");
    const atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 60;   // keep following the answer unless the reader scrolled up
    const live = t.status === "running" && !steps.some((s, k) => isRunning(s, k, steps, t)) ?
      `<div class="working"><span class="spin"></span>${steps.length ? "Working" : "Thinking"} · <b class="el">${clock((Date.now() - t.t0) / 1000)}</b></div>` : "";
    const ids = t.status === "done" ? runIdsOf(t) : [];
    el.innerHTML = (steps.length ? `<ol class="steps">${stepsHtml(steps, t)}</ol>` : "") + live +
      (t.status === "failed" ? `<div class="bad">The assistant could not finish: ${esc(plain(t.error || "unknown error"))}</div>` : "") +
      (t.reply ? `<div class="md reply">${md(plain(t.reply))}</div>` : "") +
      (ids.length ? `<div class="runs"><small class="muted">Runs in this answer <span class="tag sim">SIMULATED</span></small>` +
        ids.map(id => `<div class="rrow"><span>${esc(runLabel(t, id))}</span><button class="secondary show-run" data-run="${esc(id)}">Show on map</button></div>`).join("") + `</div>` : "") +
      (t.brief_id ? `<div class="row"><button class="ghost open-brief" data-brief="${esc(t.brief_id)}">Open the decision brief</button></div>` : "") +
      `<div class="rnote note"></div>`;
    el.querySelectorAll(".show-run").forEach(b => b.onclick = async () => {
      const note = el.querySelector(".rnote");
      if (running) { note.textContent = "A simulation is running: try again when it finishes."; return; }
      b.disabled = true; note.textContent = "Loading the run…";
      try {
        await loadRun(b.dataset.run, ids);
        el.querySelectorAll(".show-run").forEach(x => x.classList.toggle("on", x === b));
        note.textContent = "Shown in the trip strip, the junction table and on the map.";
      } catch (e) { note.innerHTML = `<span class="bad">${unavailable(e) ? "That run is not stored on this server." : `Could not load the run: ${esc(e.detail || e.message)}`}</span>`; }
      b.disabled = false;
    });
    el.querySelectorAll(".open-brief").forEach(b => b.onclick = () => openBrief(b.dataset.brief));
    if (atEnd) log.scrollTop = log.scrollHeight;
  }
  function chatUnavailable(why) {
    chatOff = true;
    $("chat-form").hidden = true; $("chat-sugg").hidden = true;
    $("chat-off").hidden = false; $("chat-off").textContent = why;
  }
  async function ask(message) {
    message = String(message || "").trim();
    if (!message || turnBusy || chatOff) return;
    turnBusy = true; $("chat-send").disabled = true; $("chat-in").value = "";
    $("chat-sugg").hidden = true;
    const log = $("chat-log");
    log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(message)}</div><div class="msg bot"></div>`);
    const t = { el: log.lastElementChild, status: "running", steps: [], seen: {}, t0: Date.now() };
    const timer = setInterval(() => { if (t.status === "running") drawTurn(t); }, 1000);
    drawTurn(t);
    try {
      const body = session ? { session_id: session, message } : { message };
      const r0 = await post("/agent/chat?async=1", body);
      session = r0.session_id || session;
      let r = r0;
      if (r0.turn_id && r0.reply == null) {   // async: poll the turn, showing steps as they arrive
        let misses = 0;
        while (true) {
          await new Promise(res => setTimeout(res, POLL_MS));
          if (Date.now() - t.t0 > TURN_LIMIT_MS) { r = { status: "failed", error: "no answer after 15 minutes", steps: t.steps }; break; }
          try { r = await get(`/agent/turns/${encodeURIComponent(r0.turn_id)}`); misses = 0; }
          catch (e) { if (unavailable(e) || ++misses >= 4) { r = { status: "failed", error: unavailable(e) ? "the server lost this question" : e.message, steps: t.steps }; break; } continue; }
          t.steps = r.steps || t.steps; t.status = r.status === "failed" || r.status === "done" ? r.status : "running";
          drawTurn(t);
          if (r.status === "done" || r.status === "failed") break;
        }
      } else r = { status: "done", ...r0 };
      Object.assign(t, { status: r.status === "failed" ? "failed" : "done", steps: r.steps || t.steps, reply: r.reply, run_ids: r.run_ids || [], brief_id: r.brief_id, error: r.error });
      if (t.brief_id) { lastBrief = t.brief_id; syncCase(); }
    } catch (e) {
      if (unavailable(e)) { t.el.previousElementSibling.remove(); t.el.remove(); chatUnavailable("The assistant is not on this server yet (it needs POST /agent/chat). Everything else on the page works without it."); }
      else Object.assign(t, { status: "failed", error: e.status ? `HTTP ${e.status}: ${e.detail || e.message}` : "API not reachable" });
    }
    clearInterval(timer);
    if (t.el.isConnected) drawTurn(t);
    turnBusy = false; $("chat-send").disabled = false;
  }
  function newChat() {
    if (turnBusy) return;
    session = null; $("chat-log").innerHTML = ""; $("chat-sugg").hidden = chatOff;
  }

  // ---------- decision brief ----------
  async function openBrief(id) {
    $("brief-modal").hidden = false; document.body.classList.add("brief-open");
    $("brief-body").innerHTML = `<p class="muted">Loading the brief…</p>`; $("brief-meta").innerHTML = "";
    try {
      const b = await get(`/briefs/${encodeURIComponent(id)}`);
      $("brief-body").innerHTML = md(plain(b.markdown) || "*(empty brief)*");
      const fps = b.fingerprints || {}, list = Array.isArray(fps) ? fps.map((f, k) => [f.run_id || f.id || (b.run_ids || [])[k] || `#${k + 1}`, f.sha256 || f.fingerprint || f]) : Object.entries(fps);
      $("brief-meta").innerHTML = `Brief <code>${esc(b.brief_id || id)}</code>${b.created_at ? ` · written ${esc(when(b.created_at))}` : ""} · ` +
        `runs: ${(b.run_ids || []).map(r => `<code>${esc(r)}</code>`).join(", ") || "–"}` +
        (list.length ? `<br>Evidence (SHA-256): ${list.map(([k, h]) => `${esc(k)} ${fp(typeof h === "string" ? h : "")}`).join(" · ")}` : "");
    } catch (e) {
      $("brief-body").innerHTML = `<p class="bad">${unavailable(e) ? "This brief is not on this server (or briefs are not available yet)." : `Could not load the brief: ${esc(e.detail || e.message)}`}</p>`;
    }
  }
  function closeBrief() { $("brief-modal").hidden = true; document.body.classList.remove("brief-open"); }

  // ---------- 4 · decision: review and decision records ----------
  let casesOn = null, current = null, caseBusy = false;
  const localLog = {};   // what this browser did per case: used when the server's case has no history of its own
  function caseOff(why) {
    casesOn = false;
    $("dec-off").hidden = false; $("dec-off").textContent = why;
    $("dec-new").hidden = true; $("case").hidden = true; $("case-list-box").hidden = true;
  }
  async function probeCases() {
    try { const l = await get("/corridor/cases"); casesOn = true; listCases(l); }
    catch (e) {
      caseOff(unavailable(e) ? "Review and decision records are not on this server yet (they need /corridor/cases). Simulating works without them."
                             : "API not running: reviews and decisions need the API (`make dev`).");
    }
    syncCase();
    if (casesOn) openFromHash();
  }
  async function openFromHash() {   // corridor.html#case=<case_id> (the Decisions page's "Open in corridor") opens that case in step 4
    const m = /(?:^#|&)case=([^&]+)/.exec(location.hash || "");
    if (!m) return;
    try {
      showCase(await get(`/corridor/cases/${encodeURIComponent(decodeURIComponent(m[1]))}`));
      $("dec").scrollIntoView({ block: "start" });
    } catch (e) { $("case-msg").innerHTML = `<span class="bad">${unavailable(e) ? "That case is not on this server." : esc(e.message)}</span>`; }
  }
  function listCases(l) {
    const cs = (Array.isArray(l) ? l : l?.cases || l?.items || []).slice().reverse().slice(0, 8);
    $("case-list-box").hidden = !cs.length;
    $("case-list").innerHTML = cs.map(c => `<button class="linkbtn" data-case="${esc(c.case_id)}">${esc(c.title || c.case_id)}</button> <small class="muted">${esc(stageName(c.stage))}${c.created_at ? " · " + esc(when(c.created_at)) : ""}</small>`).join("<br>");
    $("case-list").querySelectorAll("button").forEach(b => b.onclick = async () => {
      try { showCase(await get(`/corridor/cases/${encodeURIComponent(b.dataset.case)}`)); } catch (e) { $("case-msg").innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
    });
  }
  const stageName = s => (STAGES.find(x => x[0] === s) || [s, s || "–"])[1];
  function defaultTitle() {
    const ivs = changed?.interventions || [];
    return ivs.length ? `${ivs.map(iv => `${ivText(iv)} at ${short(point(iv.junction_id)?.name || iv.junction_id)}`).join(" + ")}` : "";
  }
  let titleFor = null;
  function syncCase() {   // called whenever results change (renderJourney) and when a brief arrives
    if (!casesOn) return;
    const ready = base && changed && base.run_id && changed.run_id && !base._fallback && !changed._fallback;
    const why = !base || !changed ? "Simulate today and with changes first (or show the assistant's runs on the map)." :
      base._fallback || changed._fallback ? "These are sample results made in the browser: simulate with the API running to send them for review." :
      vol(base) !== vol(changed) ? `Today's run and the run with changes use different traffic (${pct(vol(base))} vs ${pct(vol(changed))}).` : "";
    $("case-send").disabled = !ready || !!why || caseBusy;
    $("case-why").textContent = why || `Sends runs ${base.run_id} (today) and ${changed.run_id} (with changes)${lastBrief ? ` and brief ${lastBrief}` : ""}.`;
    const key = changed && changed.run_id;
    if (key && titleFor !== key) { titleFor = key; $("case-title").value = defaultTitle(); }
  }
  function busy(on, msg) {
    caseBusy = on;
    clearInterval(busy.t);
    document.querySelectorAll("#dec button").forEach(b => b.disabled = on || b.dataset.off === "1");
    $("case-busy").hidden = !on;
    if (on) { const t0 = Date.now(), show = () => { $("case-busy").innerHTML = `<span class="spin"></span>${esc(msg)} · <b class="el">${clock((Date.now() - t0) / 1000)}</b>`; }; show(); busy.t = setInterval(show, 1000); }
    else syncCase();
  }
  async function caseCall(path, body, msg, log) {
    if (caseBusy) return;
    $("case-msg").innerHTML = "";
    busy(true, msg);
    try {
      const c = await post(path, body);
      if (log && c && c.case_id) (localLog[c.case_id] ||= []).push({ ...log, at: new Date().toISOString() });
      showCase(c);
      get("/corridor/cases").then(listCases).catch(() => {});
    } catch (e) {
      $("case-msg").innerHTML = `<span class="bad">${esc(e.status ? `Not recorded (HTTP ${e.status}): ${e.detail || e.message}` : `Not recorded: ${e.message}`)}</span>`;
    }
    busy(false);
  }
  function caseRuns(c) {
    const fps = c.fingerprints || {};
    const fpOf = (id, k) => Array.isArray(fps) ? (fps.find(f => f && typeof f === "object" && (f.run_id || f.id) === id)?.sha256 || fps.find(f => f && typeof f === "object" && (f.run_id || f.id) === id)?.fingerprint || (typeof fps[k] === "string" ? fps[k] : ""))
                                               : fps[id] || "";
    return (c.runs || c.run_ids || []).map((x, k) => {
      const o = typeof x === "string" ? { run_id: x } : x, r = o.result && o.result.journey ? o.result : o;
      const id = o.run_id || r.run_id, cached = runCache[id] || (base?.run_id === id ? base : changed?.run_id === id ? changed : null);
      const ivs = o.interventions || r.interventions || cached?.interventions;
      return { run_id: id, volume_scale: Number(o.volume_scale ?? r.inputs?.volume_scale ?? cached?.inputs?.volume_scale ?? 1),
               total_s: o.total_s ?? (o.total_min != null ? o.total_min * 60 : null) ?? r.journey?.total_s ?? cached?.journey?.total_s, ivs, changes: ivs ? ivs.length > 0 : /base|today/i.test(o.role || o.variant_id || r.variant_id || "") ? false : null,
               fingerprint: o.fingerprint || r.fingerprint || fpOf(id, k), by: o.run_by || o.reviewer, at: o.created_at };
    });
  }
  function timeline(c) {
    const ev = c.events || c.history || c.timeline || c.log;
    const KIND = { proposed: "proposed", review: "in_review", decision: "decided" };   // the backend's event kinds
    if (Array.isArray(ev) && ev.length) return ev.map(e => {
      const b = e.body && typeof e.body === "object" ? e.body : {}, t = e.at || e.created_at || e.time || e.created;
      const decision = e.decision || b.decision, vol = e.volume_scale ?? b.volume_scale;
      return { stage: e.stage || e.type || e.action || KIND[e.kind] || e.kind, who: e.by || e.actor || e.reviewer || e.decider || e.user || e.who,
        at: typeof t === "number" && t < 1e12 ? t * 1000 : t, decision,   // epoch seconds -> ms
        what: e.what || e.summary || [b.title && `Sent for review: ${b.title}`, decision && decisionText(decision), vol != null && `Re-tested at ${pct(vol)} traffic`,
                                      e.reason || b.reason || e.note || b.note].filter(Boolean).join(": "),
        fp: e.fingerprint || e.sha256 };
    });
    const local = localLog[c.case_id] || [], out = [];
    const made = local.find(x => x.stage === "proposed");
    out.push({ stage: "proposed", who: c.created_by || c.raised_by || made?.who, at: c.created_at || made?.at,
               what: `Sent for review: today's roads and the run with changes${c.brief_id ? `, with brief ${c.brief_id}` : ""}`, fp: c.fingerprint || c.evidence_fingerprint });
    const reviews = c.reviews || (c.review ? [c.review] : null);
    (reviews || local.filter(x => x.stage === "in_review")).forEach(r => out.push({ stage: "in_review", who: r.reviewer || r.who, at: r.created_at || r.at,
      what: [r.volume_scale != null ? `Re-tested at ${pct(r.volume_scale)} traffic` : "Review note", r.note].filter(Boolean).join(": "), fp: r.fingerprint }));
    const ds = c.decisions || (c.decision && typeof c.decision === "object" ? [c.decision] : null);
    (ds || (c.stage === "decided" ? local.filter(x => x.stage === "decided").map(x => ({ ...x, decider: x.who })) : [])).forEach(d => out.push({ stage: "decided", who: d.decider || d.who,
      at: d.created_at || d.at, decision: d.decision, what: `${decisionText(d.decision)}: ${d.reason || ""}`, fp: d.fingerprint }));
    if (!ds && typeof c.decision === "string") out.push({ stage: "decided", who: c.decider, at: c.decided_at, decision: c.decision, what: `${decisionText(c.decision)}: ${c.reason || ""}`, fp: c.decision_fingerprint });
    return out;
  }
  function showCase(c) {
    current = c;
    $("dec-new").hidden = c.stage !== "decided";   // a decided case is final: a new case can be started
    $("case").hidden = false;
    const at = STAGES.findIndex(s => s[0] === c.stage), runs = caseRuns(c);
    const byVol = {};
    runs.forEach(r => { (byVol[r.volume_scale] ||= {})[r.changes ? "c" : "b"] = r; });
    const sums = Object.entries(byVol).sort((a, b) => a[0] - b[0]).filter(([, v]) => v.b?.total_s && v.c?.total_s)
      .map(([v, x]) => { const d = (x.c.total_s - x.b.total_s) / 60; return `<li>At <b>${pct(v)}</b> traffic: ${minsOf(x.b.total_s)} → ${minsOf(x.c.total_s)} min, <span class="${d < -0.05 ? "ok" : d > 0.05 ? "bad" : ""}">${signed(d)} min</span></li>`; });
    const decided = c.stage === "decided", tl = timeline(c), verdict = [...tl].reverse().find(e => e.stage === "decided");
    $("case").innerHTML =
      `<div class="case-hd"><b>${esc(c.title || "Untitled case")}</b><br><small class="muted">Case <code>${esc(c.case_id)}</code>${c.brief_id ? ` · <button class="linkbtn" id="case-brief">brief ${esc(c.brief_id)}</button>` : ""}` +
      `${decided ? "" : ` · <button class="linkbtn" id="case-another" title="This case stays open in Earlier cases">start another case</button>`}</small></div>` +
      `<ol class="stages">${STAGES.map(([k, n], i) => `<li class="${i < at ? "done" : i === at ? "now" : ""}" data-stage="${k}">${n}</li>`).join("")}</ol>` +
      (sums.length ? `<ul class="sums">${sums.join("")}</ul>` : "") +
      `<table class="caseruns"><tr><th>Traffic</th><th>Roads</th><th>Trip</th><th>Evidence</th><th></th></tr>` +
      runs.map(r => `<tr data-run="${esc(r.run_id)}"><td>${pct(r.volume_scale)}</td><td>${r.changes == null ? "–" : r.changes ? "with changes" : "today"}</td>` +
        `<td>${r.total_s ? minsOf(r.total_s) + " min" : "–"}</td><td>${fp(r.fingerprint) || "–"}</td>` +
        `<td><button class="linkbtn case-show" data-run="${esc(r.run_id)}">map</button></td></tr>`).join("") + `</table>` +
      (decided ? `<div class="note info"><b>${esc(verdict ? decisionText(verdict.decision) : "Decided")}</b>${verdict?.who ? ` by ${esc(verdict.who)}` : ""}${verdict?.at ? `, ${esc(when(verdict.at))}` : ""}. ` +
        `This record is final and append-only: it cannot be edited or deleted. Start a new case for a new proposal.</div>` :
      `<div class="role"><b>Reviewer</b> <small class="muted">re-tests the options with more or less traffic</small>
         <div class="row"><input id="rv-name" placeholder="Your name" autocomplete="name" value="${esc(store.get("cr_reviewer"))}"></div>
         <textarea id="rv-note" rows="2" placeholder="Note (optional)"></textarea>
         <div class="row"><button class="secondary" id="rv-80">Re-test at 80% traffic</button><button class="secondary" id="rv-110">Re-test at 110% traffic</button></div>
         <button class="linkbtn" id="rv-note-only">Record the note without a re-test</button></div>
       <div class="role"><b>Decider</b> <small class="muted">${c.stage === "proposed" ? "usually after a reviewer has re-tested" : "approves, rejects or sends back"}</small>
         <div class="row"><input id="dc-name" placeholder="Your name" autocomplete="name" value="${esc(store.get("cr_decider"))}"></div>
         <textarea id="dc-reason" rows="2" placeholder="Reason (required)"></textarea>
         <div class="row"><button id="dc-approve" class="ok-b">Approve</button><button id="dc-reject" class="bad-b">Reject</button><button id="dc-revise" class="ghost">Revise</button></div></div>`) +
      `<div class="tl-hd"><b>Record</b> <small class="muted">who, when, what · append-only, each step fingerprinted (SHA-256)</small></div>` +
      `<ol class="tl">${tl.map(e => `<li data-stage="${esc(e.stage)}"><span class="st">${esc(stageName(e.stage))}</span> <b>${esc(e.who || "–")}</b>` +
        ` <small class="muted">${esc(when(e.at))}</small><br>${esc(e.what || "")}${e.fp ? ` <span class="muted">· evidence</span> ${fp(e.fp)}` : ""}</li>`).join("")}</ol>`;
    $("case").querySelectorAll(".case-show").forEach(b => b.onclick = () => { if (!running) loadRun(b.dataset.run, runs.map(r => r.run_id)).catch(e => { $("case-msg").innerHTML = `<span class="bad">${unavailable(e) ? "That run is not stored on this server." : esc(e.message)}</span>`; }); });
    if ($("case-brief")) $("case-brief").onclick = () => openBrief(c.brief_id);
    if ($("case-another")) $("case-another").onclick = () => { current = null; $("case").hidden = true; $("dec-new").hidden = false; $("case-msg").innerHTML = ""; syncCase(); };
    if (decided) return;
    const review = v => {
      const who = $("rv-name").value.trim(), note = $("rv-note").value.trim();
      if (!who) { $("case-msg").innerHTML = `<span class="bad">Enter the reviewer's name first.</span>`; $("rv-name").focus(); return; }
      if (v == null && !note) { $("case-msg").innerHTML = `<span class="bad">Write a note first.</span>`; return; }
      store.set("cr_reviewer", who);
      const body = { reviewer: who, ...(v != null ? { volume_scale: v } : {}), ...(note ? { note } : {}) };
      caseCall(`/corridor/cases/${encodeURIComponent(c.case_id)}/review`, body, v != null ? `Re-testing both options at ${pct(v)} traffic, usually a few minutes` : "Recording the note",
               { stage: "in_review", who, volume_scale: v, note });
    };
    $("rv-80").onclick = () => review(0.8); $("rv-110").onclick = () => review(1.1); $("rv-note-only").onclick = () => review(null);
    const decide = d => {
      const who = $("dc-name").value.trim(), reason = $("dc-reason").value.trim();
      if (!who) { $("case-msg").innerHTML = `<span class="bad">Enter the decider's name first.</span>`; $("dc-name").focus(); return; }
      if (reason.length < 3) { $("case-msg").innerHTML = `<span class="bad">A reason is required: it goes on the record with the decision.</span>`; $("dc-reason").focus(); return; }
      store.set("cr_decider", who);
      caseCall(`/corridor/cases/${encodeURIComponent(c.case_id)}/decide`, { decider: who, decision: d, reason }, "Recording the decision", { stage: "decided", who, decision: d, reason });
    };
    $("dc-approve").onclick = () => decide("approve"); $("dc-reject").onclick = () => decide("reject"); $("dc-revise").onclick = () => decide("revise");
  }
  function sendForReview() {
    if (!base || !changed) return;
    const title = $("case-title").value.trim() || defaultTitle() || "Corridor change";
    const who = $("case-by").value.trim();
    if (who) store.set("cr_proposer", who);
    const body = { title, run_ids: [base.run_id, changed.run_id], ...(lastBrief ? { brief_id: lastBrief } : {}), ...(who ? { created_by: who } : {}) };
    caseCall("/corridor/cases", body, "Recording the proposal", { stage: "proposed", who });
  }

  // ---------- wiring ----------
  $("ask-open").onclick = () => openChat($("chat").hidden);
  $("chat-close").onclick = () => openChat(false);
  $("chat-new").onclick = newChat;
  $("chat-sugg").innerHTML = SUGGESTIONS.map(s => `<button class="sugg">${esc(s)}</button>`).join("");
  $("chat-sugg").querySelectorAll("button").forEach(b => b.onclick = () => ask(b.textContent));
  $("chat-form").onsubmit = e => { e.preventDefault(); ask($("chat-in").value); };
  $("chat-in").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask($("chat-in").value); } };
  $("brief-close").onclick = closeBrief;
  $("brief-print").onclick = () => window.print();
  $("brief-modal").onclick = e => { if (e.target === $("brief-modal")) closeBrief(); };
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("brief-modal").hidden) closeBrief(); });
  $("case-send").onclick = sendForReview;
  $("case-by").value = store.get("cr_proposer");
  probeCases();

  return { md, ask, loadRun, openBrief, showCase, timeline, openFromHash, sync: syncCase, get session() { return session; }, get current() { return current; } };
})();
