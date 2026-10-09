// Shared mockup helpers for both design directions. Theme is passed in by each page;
// nothing here is final product code, it renders the static mockups from data.js.
(function () {
  const D = window.CR;
  const $ = (s, r = document) => r.querySelector(s);
  const fmt = (n, d = 1) => Number(n).toFixed(d);

  // --- Derived demo numbers --------------------------------------------------------
  // REAL: TomTom typical July day legs. SIMULATED rows are illustrative for the mockup.
  // Illustrative numbers matching the team's real run totals (TomTom 56.2, model 55.4,
  // Nanal Nagar + Rethibowli flyover -2.1 +/- 0.9). Per-leg split is illustrative.
  const real = [6.5, 13.3, 3.9, 3.0, 2.4, 2.8, 4.5, 4.0, 1.2, 7.2, 2.4, 5.0];
  const sim = [6.8, 12.9, 4.1, 3.0, 2.3, 2.8, 4.6, 4.2, 1.3, 7.0, 2.3, 4.1];
  const chg = [6.8, 12.9, 4.1, 3.0, 2.3, 2.8, 4.6, 3.4, 0.6, 6.1, 2.6, 4.1];
  const sum = a => +a.reduce((s, x) => s + x, 0).toFixed(1);
  const hourly = D.days.filter(d => /^Typical July day \(\d\d-\d\d\)$/.test(d.label) && d.label !== "Typical July day (06-23)").map(d => d.min);
  window.CRX = { real, sim, chg, sum, hourly, noise: 0.9 };

  // --- Speed colour ---------------------------------------------------------------
  function speedColor(kmh, t) { return kmh >= 25 ? t.fast : kmh >= 15 ? t.mid : t.slow; }

  // --- SVG route (home pages, offline) ----------------------------------------------
  window.routeSVG = function (el, t, opts = {}) {
    const all = D.route.features.flatMap(f => f.geometry.coordinates);
    const xs = all.map(c => c[0]), ys = all.map(c => c[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const W = opts.w || 600, H = opts.h || 360, pad = opts.pad || 28;
    const k = Math.min((W - 2 * pad) / (maxX - minX), (H - 2 * pad) / ((maxY - minY) * 1.05));
    const ox = (W - (maxX - minX) * k) / 2, oy = (H - (maxY - minY) * 1.05 * k) / 2;
    const P = ([x, y]) => [ox + (x - minX) * k, oy + (maxY - y) * 1.05 * k];
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" aria-label="Corridor route coloured by measured speed">`;
    if (t.glow) s += `<defs><filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter></defs>`;
    D.route.features.forEach(f => {
      const d = f.geometry.coordinates.map((c, i) => (i ? "L" : "M") + P(c).map(v => v.toFixed(1)).join(",")).join("");
      const col = speedColor(f.properties.speed, t);
      if (t.glow) s += `<path d="${d}" fill="none" stroke="${col}" stroke-width="9" stroke-linecap="round" opacity=".55" filter="url(#glow)"/>`;
      if (t.casing) s += `<path d="${d}" fill="none" stroke="${t.casing}" stroke-width="${(opts.sw || 5) + 4}" stroke-linecap="round" stroke-linejoin="round"/>`;
      s += `<path d="${d}" fill="none" stroke="${col}" stroke-width="${opts.sw || 5}" stroke-linecap="round" stroke-linejoin="round"/>`;
    });
    D.points.forEach((p, i) => {
      const [x, y] = P([p.lon, p.lat]);
      if (p.kind === "end") s += `<circle cx="${x}" cy="${y}" r="9" fill="${t.endFill}" stroke="${t.endStroke}" stroke-width="2"/><text x="${x}" y="${y + 3.5}" text-anchor="middle" font-size="10" font-weight="700" fill="${t.endText}" font-family="inherit">${i ? "B" : "A"}</text>`;
      else s += `<circle cx="${x}" cy="${y}" r="${p.id === opts.sel ? 6 : 3.5}" fill="${p.id === opts.sel ? t.sel : t.node}" stroke="${t.nodeStroke}" stroke-width="1.5"/>`;
    });
    if (opts.labels) {
      [["A_lingampally", "Lingampally", -1, 0], ["j03", "Gachibowli", 1, 0], ["j07", "Tolichowki", -1, 16], ["B_lakdikapul", "Lakdikapul", 0, 24]].forEach(([id, name, side, dy]) => {
        const p = D.points.find(q => q.id === id); const [x, y] = P([p.lon, p.lat]);
        s += `<text x="${x + 14 * side}" y="${y + 4 + dy}" text-anchor="${side > 0 ? "start" : side < 0 ? "end" : "middle"}" font-size="11" fill="${t.label}" font-family="inherit" font-weight="500">${name}</text>`;
      });
    }
    el.innerHTML = s + "</svg>";
  };

  // --- Hour histogram picker ----------------------------------------------------------
  window.hourBars = function (el, t, sel = 18) {
    const max = Math.max(...hourly);
    el.innerHTML = hourly.map((m, h) => `<button class="hb${h === sel ? " on" : ""}" title="${String(h).padStart(2, "0")}:00, ${fmt(m)} min (TomTom, typical July)" style="--h:${(m / max * 100).toFixed(0)}%"><i></i></button>`).join("");
  };

  // --- Trip strip -------------------------------------------------------------------
  // rows: [{key, tag, tagClass, name, sub, legs, cls}]
  window.tripStrip = function (el, rows, opt = {}) {
    const max = Math.max(...rows.map(r => sum(r.legs)));
    const base = sum(real);
    const html = rows.map((r, ri) => {
      const tot = sum(r.legs);
      const width = (tot / max * 100).toFixed(2);
      const segs = r.legs.map((m, i) => {
        const delta = r.key === "chg" ? +(m - sim[i]).toFixed(1) : 0;
        const dcls = delta <= -0.5 ? "good" : delta >= 0.3 ? "bad" : "";
        return `<div class="seg ${r.cls}${i === opt.selLeg ? " sel" : ""}${dcls ? " " + dcls : ""}" style="flex:${m}" title="${D.legs[i].from} → ${D.legs[i].to}: ${fmt(m)} min">` +
          (dcls && m >= 1.6 ? `<span class="m d ${dcls}">${delta > 0 ? "+" : "−"}${fmt(Math.abs(delta))}</span>` : `<span class="m">${m >= 1.6 ? fmt(m) : ""}</span>`) + `</div>`;
      }).join("");
      let delta = "";
      if (r.key === "sim") delta = `<span class="dl neutral" title="Model vs TomTom">${tot - base >= 0 ? "+" : "−"}${fmt(Math.abs(tot - base))} <small>vs real</small></span>`;
      if (r.key === "chg") { const d = tot - sum(sim); delta = `<span class="dl ${d < -window.CRX.noise ? "good" : "neutral"}">${d >= 0 ? "+" : "−"}${fmt(Math.abs(d))} <small>± ${fmt(window.CRX.noise)}</small></span>`; }
      if (r.key === "real") delta = `<span class="dl muted">baseline</span>`;
      return `<div class="sr"><div class="sl"><span class="tag ${r.tagClass}">${r.tag}</span><span class="sn">${r.name}</span>${r.sub ? `<span class="ss">${r.sub}</span>` : ""}</div>` +
        `<div class="sb"><div class="bar" style="width:${width}%">${segs}</div></div>` +
        `<div class="st"><b>${fmt(tot)}</b><span class="u">min</span>${delta}</div></div>`;
    }).join("");
    // junction ticks under the REAL row
    let acc = 0; const tot0 = sum(real);
    const ticks = D.points.map((p, i) => { const pos = (acc / tot0) * (tot0 / max) * 100; if (i < real.length) acc += real[i]; return `<span style="left:${pos.toFixed(2)}%">${p.kind === "end" ? (i ? "B" : "A") : i}</span>`; }).join("");
    el.innerHTML = html + `<div class="sr ticks"><div class="sl"></div><div class="sb"><div class="tk">${ticks}</div></div><div class="st"></div></div>`;
  };

  // --- Live junction table ------------------------------------------------------------
  window.liveRows = function (el, n = 6, opt = {}) {
    const rows = [...D.live].sort((a, b) => (b.delay - b.usual) - (a.delay - a.usual)).slice(0, n);
    el.innerHTML = rows.map(j => {
      const ratio = j.usual ? j.delay / j.usual : 1;
      const sev = ratio >= 3 ? "hi" : ratio >= 1.4 ? "md" : "lo";
      const num = D.points.findIndex(p => p.id === j.id);
      return `<tr class="${j.id === opt.sel ? "sel" : ""}"><td><span class="jn">${num}</span></td><td class="nm"><b>${j.name}</b><small>${j.worst.replace(/ Bound/, "-bound")}</small></td>` +
        `<td class="num ${sev}">${Math.round(j.delay)}<small>s</small></td><td class="num mut">${Math.round(j.usual)}<small>s</small></td><td class="num">${j.queue}<small>m</small></td></tr>`;
    }).join("");
  };

  // --- MapLibre corridor map --------------------------------------------------------
  window.corridorMap = function (id, t, opt = {}) {
    if (!window.maplibregl) return null;
    const map = new maplibregl.Map({
      container: id, style: t.style, attributionControl: false,
      center: [78.392, 17.432], zoom: 11.6, pitch: opt.pitch ?? 48, bearing: opt.bearing ?? -18,
      interactive: true, fadeDuration: 0,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.on("load", () => {
      const all = D.route.features.flatMap(f => f.geometry.coordinates);
      const b = all.reduce((bb, c) => bb.extend(c), new maplibregl.LngLatBounds(all[0], all[0]));
      map.fitBounds(b, { padding: opt.padding || 60, pitch: opt.pitch ?? 48, bearing: opt.bearing ?? -18, duration: 0 });
      if (t.tune) t.tune(map);
      map.addSource("route", { type: "geojson", data: D.route });
      const colorExpr = ["step", ["get", "speed"], t.slow, 15, t.mid, 25, t.fast];
      if (t.glow) map.addLayer({ id: "route-glow", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colorExpr, "line-width": 16, "line-blur": 10, "line-opacity": 0.55 } });
      if (t.casing) map.addLayer({ id: "route-case", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": t.casing, "line-width": 9 } });
      map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colorExpr, "line-width": 5 } });
      map.addSource("veh", { type: "geojson", data: { type: "FeatureCollection", features: D.vehicles.map(v => ({ type: "Feature", properties: { k: v[2] }, geometry: { type: "Point", coordinates: [v[0], v[1]] } })) } });
      map.addLayer({ id: "veh", type: "circle", source: "veh", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.2, 15, 4.5], "circle-color": ["match", ["get", "k"], "2w", t.v2w, "car", t.vcar, "auto", t.vauto, t.vbus], "circle-opacity": 0.95, "circle-stroke-width": t.vstroke ? 0.6 : 0, "circle-stroke-color": t.vstroke || "#000" } });
      D.points.forEach((p, i) => {
        const el = document.createElement("div");
        const sel = p.id === opt.sel;
        el.className = "jm" + (p.kind === "end" ? " end" : "") + (sel ? " sel" : "") + (opt.fly && opt.fly.includes(p.id) ? " fly" : "");
        el.innerHTML = p.kind === "end" ? (i ? "B" : "A") : String(i);
        new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([p.lon, p.lat]).addTo(map);
      });
      if (opt.callout) {
        const p = D.points.find(q => q.id === opt.sel);
        const el = document.createElement("div"); el.className = "callout"; el.innerHTML = opt.callout;
        new maplibregl.Marker({ element: el, anchor: "top", offset: [0, 20] }).setLngLat([p.lon, p.lat]).addTo(map);
      }
      document.documentElement.classList.add("map-ready");
    });
    return map;
  };
})();
