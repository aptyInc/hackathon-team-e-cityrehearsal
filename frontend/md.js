// CityRehearsal: tiny, safe markdown for the assistant's replies and decision briefs (corridor.html via planner.js,
// decisions.html). Everything is HTML-escaped first; then headings, bold, italic, code, lists, tables, quotes, rules.
// window.crMarkdown = {md, inline, esc}. Owner: Frontend.
window.crMarkdown = (() => {
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  function inline(s) {   // `code` is kept as it is; **bold** and *italic* elsewhere
    return String(s ?? "").split(/(`[^`]+`)/).map((part, k) => k % 2 ? `<code>${esc(part.slice(1, -1))}</code>` :
      esc(part).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,;:!?]|$)/g, "$1<i>$2</i>")).join("");
  }
  const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
  function md(src) {
    const L = String(src ?? "").replace(/\r\n?/g, "\n").split("\n"), out = [];
    const isList = l => /^\s*([-*+]|\d+[.)])\s+/.test(l), isTableSep = l => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
    for (let i = 0; i < L.length;) {
      const l = L[i];
      if (!l.trim()) { i++; continue; }
      if (/^```/.test(l)) {   // fenced code
        const buf = []; i++;
        while (i < L.length && !/^```/.test(L[i])) buf.push(L[i++]);
        i++; out.push(`<pre>${esc(buf.join("\n"))}</pre>`); continue;
      }
      let m = /^(#{1,6})\s+(.*)$/.exec(l);
      if (m) { out.push(`<div class="md-h md-h${Math.min(m[1].length, 4)}">${inline(m[2].replace(/\s#+\s*$/, ""))}</div>`); i++; continue; }
      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l)) { out.push("<hr>"); i++; continue; }
      if (l.trim().startsWith("|") && i + 1 < L.length && isTableSep(L[i + 1])) {
        const head = cells(l); i += 2; const rows = [];
        while (i < L.length && L[i].trim().startsWith("|")) rows.push(cells(L[i++]));
        out.push(`<div class="md-tw"><table class="md-t"><tr>${head.map(c => `<th>${inline(c)}</th>`).join("")}</tr>` +
          rows.map(r => `<tr>${head.map((_, k) => `<td>${inline(r[k] ?? "")}</td>`).join("")}</tr>`).join("") + `</table></div>`);
        continue;
      }
      if (isList(l)) {
        const ordered = /^\s*\d/.test(l), items = [];
        while (i < L.length && (isList(L[i]) || (L[i].trim() && /^\s{2,}/.test(L[i]) && items.length))) {
          if (isList(L[i])) items.push(L[i].replace(/^\s*([-*+]|\d+[.)])\s+/, "")); else items[items.length - 1] += " " + L[i].trim();
          i++;
        }
        out.push(`<${ordered ? "ol" : "ul"}>${items.map(x => `<li>${inline(x)}</li>`).join("")}</${ordered ? "ol" : "ul"}>`);
        continue;
      }
      if (/^\s*>/.test(l)) {
        const buf = [];
        while (i < L.length && /^\s*>/.test(L[i])) buf.push(L[i++].replace(/^\s*>\s?/, ""));
        out.push(`<div class="md-q">${inline(buf.join(" "))}</div>`); continue;
      }
      const buf = [];
      while (i < L.length && L[i].trim() && !/^(#{1,6}\s|```|\s*>)/.test(L[i]) && !isList(L[i]) && !(L[i].trim().startsWith("|") && isTableSep(L[i + 1] || ""))) buf.push(L[i++].trim());
      out.push(`<p>${buf.map(inline).join("<br>")}</p>`);
    }
    return out.join("");
  }
  return { md, inline, esc };
})();
