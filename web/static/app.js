/* eztoollinux web UI */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtSize = (n) => {
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(1) + " GB";
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(1) + " KB";
  return n + " B";
};

const state = {
  tools: [],
  tool: null,
  mode: "upload",        // upload | server
  files: [],             // File objects
  serverPath: null,      // {path, dir}
  browseDir: "",
  format: null,
  job: null,
  poll: null,
  // table viewer
  file: null,
  q: "",
  sort: null,
  sortDir: "asc",
  offset: 0,
  limit: 100,
};

/* ---------- sidebar ---------- */
async function loadTools() {
  state.tools = await (await fetch("/api/tools")).json();
  renderToolList();
  selectTool(state.tools[0]);
}

function renderToolList() {
  const filter = $("tool-filter").value.toLowerCase();
  $("tool-list").innerHTML = state.tools
    .filter((t) => (t.name + t.desc).toLowerCase().includes(filter))
    .map((t) => `<button class="tool-item${state.tool && t.id === state.tool.id ? " active" : ""}"
      data-id="${t.id}">${esc(t.name)}<small>${esc(t.desc)}</small></button>`)
    .join("");
}

$("tool-filter").addEventListener("input", renderToolList);
$("tool-list").addEventListener("click", (e) => {
  const btn = e.target.closest(".tool-item");
  if (btn) selectTool(state.tools.find((t) => t.id === btn.dataset.id));
});

function selectTool(tool) {
  state.tool = tool;
  state.files = [];
  state.serverPath = null;
  state.format = tool.outputs[0];
  state.helpLoaded = false;
  $("help-summary").textContent = "Command-line help for " + tool.name + " (all options)";
  $("help-text").textContent = "Loading...";
  if ($("help-details").open) loadHelp();
  $("known-paths").innerHTML = (tool.paths || []).length
    ? '<span class="kp-title">Known Windows locations</span>' +
      tool.paths.map((p) => "<code>" + esc(p) + "</code>").join("")
    : "";
  $("tool-name").textContent = tool.name;
  $("tool-desc").textContent = tool.desc;
  $("drop-hint").textContent = "expected: " + tool.hint;
  $("file-input").multiple = tool.input !== "file";
  $("format-seg").innerHTML = tool.outputs
    .map((f) => `<button class="seg-btn${f === state.format ? " active" : ""}"
      data-fmt="${f}">${f === "stdout" ? "text" : f}</button>`)
    .join("");
  renderToolList();
  renderFiles();
  renderServerPick();
  updatePreview();
}

$("format-seg").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  state.format = btn.dataset.fmt;
  [...$("format-seg").children].forEach((b) => b.classList.toggle("active", b === btn));
  updatePreview();
});

/* ---------- evidence: upload ---------- */
const dropZone = $("drop-zone");
$("file-input").addEventListener("change", (e) => addFiles([...e.target.files]));
["dragover", "dragleave", "drop"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropZone.classList.toggle("drag", ev === "dragover");
    if (ev === "drop") addFiles([...e.dataTransfer.files]);
  }));

function addFiles(files) {
  if (!files.length) return;
  state.files = state.tool.input === "file" ? [files[0]] : state.files.concat(files);
  renderFiles();
  updatePreview();
}

function renderFiles() {
  $("file-chips").innerHTML = state.files
    .map((f, i) => `<li>${esc(f.name)}<span>${fmtSize(f.size)}</span>
      <span class="rm" data-i="${i}" style="cursor:pointer">x</span></li>`)
    .join("");
}
$("file-chips").addEventListener("click", (e) => {
  if (!e.target.classList.contains("rm")) return;
  state.files.splice(+e.target.dataset.i, 1);
  renderFiles();
  updatePreview();
});

/* ---------- evidence: /data browser ---------- */
$("input-mode").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  state.mode = btn.dataset.mode;
  [...$("input-mode").children].forEach((b) => b.classList.toggle("active", b === btn));
  $("upload-pane").hidden = state.mode !== "upload";
  $("server-pane").hidden = state.mode !== "server";
  if (state.mode === "server") browse(state.browseDir);
  updatePreview();
});

async function browse(path) {
  state.browseDir = path;
  const data = await (await fetch("/api/browse?path=" + encodeURIComponent(path))).json();
  $("browse-path").textContent = "/data" + (path ? "/" + path : "");
  if (data.error) {
    $("browse-list").innerHTML = `<li class="empty">${esc(data.error)} - start the container with -v /your/evidence:/data</li>`;
    return;
  }
  $("browse-list").innerHTML = (data.entries.length ? data.entries : [])
    .map((e2) => `<li class="${e2.dir ? "is-dir" : "is-file"}" data-name="${esc(e2.name)}"
      data-dir="${e2.dir}">${e2.dir ? "&#9656; " : ""}${esc(e2.name)}
      <span>${e2.dir ? "open / select" : fmtSize(e2.size)}</span></li>`)
    .join("") || '<li class="empty">empty folder - click "select this folder" below if the tool takes a folder</li>';
  renderServerPick();
}

$("browse-up").addEventListener("click", () => {
  const parts = state.browseDir.split("/").filter(Boolean);
  parts.pop();
  browse(parts.join("/"));
});

$("browse-list").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-name]");
  if (!li) return;
  const name = li.dataset.name;
  const full = (state.browseDir ? state.browseDir + "/" : "") + name;
  if (li.dataset.dir === "true") {
    if (state.tool.input !== "file" && e.target.tagName === "SPAN") {
      state.serverPath = { path: full, dir: true };
    } else {
      browse(full);
      return;
    }
  } else {
    if (state.tool.input === "dir") return;
    state.serverPath = { path: full, dir: false };
  }
  renderServerPick();
  updatePreview();
});

function renderServerPick() {
  const el = $("server-pick");
  if (state.serverPath) {
    el.hidden = false;
    el.textContent = "selected: /data/" + state.serverPath.path +
      (state.serverPath.dir ? "/ (folder)" : "");
  } else if (state.tool && state.tool.input !== "file") {
    el.hidden = false;
    el.textContent = 'tip: click a folder name to open it, click its "open / select" label to use it as input';
  } else {
    el.hidden = true;
  }
}

/* ---------- command preview + run ---------- */
$("args-input").addEventListener("input", updatePreview);

function currentInput() {
  if (state.mode === "upload" && state.files.length) {
    const many = state.files.length > 1;
    return { label: many ? "input/" : state.files[0].name, dir: many, ok: true };
  }
  if (state.mode === "server" && state.serverPath) {
    return { label: "/data/" + state.serverPath.path, dir: state.serverPath.dir, ok: true };
  }
  return { label: "<input>", dir: false, ok: false };
}

function updatePreview() {
  if (!state.tool) return;
  const inp = currentInput();
  if (state.tool.runner === "allez") {
    const extraA = $("args-input").value.trim();
    $("cmd-preview").innerHTML =
      '<span class="p">$</span> <span class="t">allez</span>' +
      ' <span class="fl">-s</span> <span class="v">' + esc(inp.label) + "</span>" +
      ' <span class="fl">-o</span> <span class="v">output/</span>' +
      (extraA ? " " + esc(extraA) : "");
    $("run-btn").disabled = !inp.ok || state.job?.status === "running";
    return;
  }
  const flag = inp.dir ? "-d" : "-f";
  let out = "";
  if (state.format === "csv") out = ' <span class="fl">--csv</span> <span class="v">output/</span>';
  else if (state.format === "json") out = ' <span class="fl">--json</span> <span class="v">output/</span>';
  else if (state.format === "files") out = ' <span class="fl">--out</span> <span class="v">output/</span>';
  const extra = $("args-input").value.trim();
  $("cmd-preview").innerHTML =
    '<span class="p">$</span> <span class="t">' + esc(state.tool.name.toLowerCase()) + "</span>" +
    ' <span class="fl">' + flag + '</span> <span class="v">' + esc(inp.label) + "</span>" +
    out + (extra ? " " + esc(extra) : "");
  $("run-btn").disabled = !inp.ok || state.job?.status === "running";
}

$("run-btn").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("tool", state.tool.id);
  fd.append("format", state.format);
  fd.append("args", $("args-input").value.trim());
  if (state.mode === "upload") state.files.forEach((f) => fd.append("files", f));
  else fd.append("path", state.serverPath.path);

  $("run-btn").disabled = true;
  $("results-card").hidden = false;
  setStatus("running", "uploading evidence...");
  $("out-files").innerHTML = "";
  $("viewer").hidden = true;
  $("stdout").textContent = "";
  $("sql-open").hidden = true;
  $("sql-panel").hidden = true;
  state.schema = null;

  const res = await fetch("/api/run", { method: "POST", body: fd });
  if (!res.ok) {
    setStatus("error", await res.text());
    updatePreview();
    return;
  }
  const { id } = await res.json();
  state.job = { id, status: "running" };
  setStatus("running", "running " + state.tool.name + "...");
  clearInterval(state.poll);
  state.poll = setInterval(pollJob, 900);
});

function setStatus(cls, text) {
  $("status-dot").className = "dot " + cls;
  $("status-text").textContent = text;
}

async function pollJob() {
  const job = await (await fetch("/api/jobs/" + state.job.id)).json();
  state.job = job;
  $("stdout").textContent = job.stdout || "";
  if (job.status === "running") return;
  clearInterval(state.poll);
  updatePreview();
  if (job.status === "error") {
    setStatus("error", "failed (exit " + job.returncode + ") - see the output log below");
    $("stdout").parentElement.open = true;
    return;
  }
  setStatus("done", job.files.length
    ? "done - " + job.files.length + " output file" + (job.files.length > 1 ? "s" : "")
    : "done - no output files (see the output log)");
  $("out-files").innerHTML = job.files
    .map((f) => `<button class="out-file" data-name="${esc(f.name)}">${esc(f.name)}
      <span>${fmtSize(f.size)}</span></button>`)
    .join("");
  if (!job.files.length && job.stdout) $("stdout").parentElement.open = true;
  const queryable = job.files.some((f) => /\.(csv|tsv|json|jsonl|db)$/i.test(f.name));
  $("sql-open").hidden = !queryable;
  const first = job.files.find((f) => /\.(csv|tsv|json|jsonl)$/i.test(f.name)) || job.files[0];
  if (first) openFile(first.name);
  if (queryable && state.tool.runner === "allez") openSql();
}

/* ---------- output viewer ---------- */
$("out-files").addEventListener("click", (e) => {
  const btn = e.target.closest(".out-file");
  if (btn) openFile(btn.dataset.name);
});

function openFile(name) {
  state.file = name;
  state.q = "";
  state.sort = null;
  state.offset = 0;
  $("table-q").value = "";
  [...$("out-files").children].forEach((b) =>
    b.classList.toggle("active", b.dataset.name === name));
  $("viewer").hidden = false;
  $("dl-link").href = "/api/jobs/" + state.job.id + "/download?file=" + encodeURIComponent(name);
  if (/\.(csv|tsv|json|jsonl)$/i.test(name)) {
    $("text-view").hidden = true;
    $("table-wrap").hidden = false;
    $("table-q").disabled = false;
    loadTable();
  } else {
    $("table-wrap").hidden = true;
    $("table-q").disabled = true;
    $("table-count").textContent = "";
    $("pg-label").textContent = "";
    loadText(name);
  }
}

async function loadText(name) {
  const el = $("text-view");
  el.hidden = false;
  const data = await (await fetch("/api/jobs/" + state.job.id +
    "/text?file=" + encodeURIComponent(name))).json();
  el.textContent = data.text +
    (data.size > data.text.length ? "\n\n[truncated - download the file for the rest]" : "");
}

let qTimer = null;
$("table-q").addEventListener("input", () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => {
    state.q = $("table-q").value.trim();
    state.offset = 0;
    loadTable();
  }, 300);
});

$("pg-prev").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  loadTable();
});
$("pg-next").addEventListener("click", () => {
  state.offset += state.limit;
  loadTable();
});

async function loadTable() {
  const p = new URLSearchParams({
    file: state.file, q: state.q,
    offset: state.offset, limit: state.limit,
  });
  if (state.sort !== null) { p.set("sort", state.sort); p.set("dir", state.sortDir); }
  const res = await fetch("/api/jobs/" + state.job.id + "/table?" + p);
  if (!res.ok) { $("table-wrap").innerHTML = "<p style='padding:12px'>" + esc(await res.text()) + "</p>"; return; }
  const data = await res.json();
  if (state.offset >= data.filtered) state.offset = Math.max(0, Math.floor((data.filtered - 1) / state.limit) * state.limit);

  const hi = (cell) => {
    let out = esc(cell);
    if (state.q) {
      const rx = new RegExp("(" + state.q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      out = out.replace(rx, "<mark>$1</mark>");
    }
    return out;
  };
  $("table-wrap").innerHTML =
    "<table><thead><tr>" +
    data.headers.map((h, i) =>
      `<th data-i="${i}" class="${state.sort === i ? "sorted" : ""}">${esc(h)}${
        state.sort === i ? (state.sortDir === "asc" ? " &#9652;" : " &#9662;") : ""}</th>`).join("") +
    "</tr></thead><tbody>" +
    data.rows.map((r) => "<tr>" + r.map((c) => `<td title="${esc(c)}">${hi(c)}</td>`).join("") + "</tr>").join("") +
    "</tbody></table>";
  $("table-wrap").querySelector("thead").addEventListener("click", (e) => {
    const th = e.target.closest("th");
    if (!th) return;
    const i = +th.dataset.i;
    if (state.sort === i) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    else { state.sort = i; state.sortDir = "asc"; }
    state.offset = 0;
    loadTable();
  });
  const from = data.filtered ? state.offset + 1 : 0;
  const to = Math.min(state.offset + state.limit, data.filtered);
  $("table-count").textContent = data.filtered.toLocaleString() + " rows" +
    (state.q ? " match" : "") + (data.truncated ? " (first 200k loaded)" : "");
  $("pg-label").textContent = from + "-" + to;
  $("pg-prev").disabled = state.offset === 0;
  $("pg-next").disabled = to >= data.filtered;
}

/* ---------- SQL console ---------- */
const SQL_KEYWORDS = [
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "LIKE", "GLOB", "IN", "IS",
  "NULL", "ORDER BY", "GROUP BY", "HAVING", "LIMIT", "OFFSET", "DISTINCT",
  "COUNT(*)", "COUNT", "MIN", "MAX", "SUM", "AVG", "AS", "ASC", "DESC",
  "BETWEEN", "CASE", "WHEN", "THEN", "ELSE", "END", "JOIN", "LEFT JOIN",
  "ON", "UNION", "UNION ALL", "CAST", "LOWER", "UPPER", "LENGTH", "SUBSTR",
];

$("sql-open").addEventListener("click", openSql);

async function openSql() {
  $("sql-panel").hidden = false;
  $("sql-open").hidden = true;
  if (state.schema) return;
  $("sql-db-name").textContent = "building database...";
  $("sql-tables").innerHTML = "";
  const res = await fetch("/api/jobs/" + state.job.id + "/db", { method: "POST" });
  if (!res.ok) {
    $("sql-db-name").textContent = "database error: " + esc(await res.text());
    return;
  }
  state.schema = await res.json();
  renderSchema();
  if (!$("sql-input").value && state.schema.tables.length) {
    $("sql-input").value = 'SELECT * FROM "' + state.schema.tables[0].name + '" LIMIT 100';
  }
}

function renderSchema() {
  const s = state.schema;
  $("sql-db-name").textContent = s.db + " - " + s.tables.length + " table" +
    (s.tables.length === 1 ? "" : "s");
  $("sql-tables").innerHTML = s.tables.map((t, i) =>
    `<details class="sql-table"${i === 0 ? " open" : ""}>
      <summary><button class="sql-tbl-name" data-t="${esc(t.name)}" type="button"
        title="Insert a SELECT for this table">${esc(t.name)}</button>
        <span>${t.rows.toLocaleString()} rows</span></summary>
      <ul>${t.columns.map((c) =>
        `<li><button class="sql-col-name" data-c="${esc(c.name)}" type="button"
          title="Insert column name">${esc(c.name)}</button></li>`).join("")}</ul>
    </details>`).join("");
}

$("sql-tables").addEventListener("click", (e) => {
  const tbl = e.target.closest(".sql-tbl-name");
  const col = e.target.closest(".sql-col-name");
  if (tbl) {
    e.preventDefault();
    $("sql-input").value = 'SELECT * FROM "' + tbl.dataset.t + '" LIMIT 100';
    $("sql-input").focus();
  } else if (col) {
    insertAtCaret($("sql-input"), quoteIdent(col.dataset.c));
  }
});

function quoteIdent(name) {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) ? name : '"' + name.replace(/"/g, '""') + '"';
}

function insertAtCaret(el, text) {
  const s = el.selectionStart, epos = el.selectionEnd;
  el.value = el.value.slice(0, s) + text + el.value.slice(epos);
  el.selectionStart = el.selectionEnd = s + text.length;
  el.focus();
}

$("sql-run").addEventListener("click", runSql);
$("sql-input").addEventListener("keydown", (e) => {
  if (acKeydown(e)) return;
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runSql(); }
});

async function runSql() {
  hideAc();
  const sql = $("sql-input").value.trim();
  if (!sql || !state.job) return;
  $("sql-status").textContent = "running...";
  const res = await fetch("/api/jobs/" + state.job.id + "/db/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql }),
  });
  const data = await res.json().catch(async () => ({ error: "query failed" }));
  const box = $("sql-results");
  box.hidden = false;
  if (data.error) {
    $("sql-status").textContent = "";
    box.innerHTML = '<p class="sql-error">' + esc(data.error) + "</p>";
    return;
  }
  $("sql-status").textContent = data.rows.length.toLocaleString() + " row" +
    (data.rows.length === 1 ? "" : "s") + (data.truncated ? " (showing first 1000)" : "");
  box.innerHTML = "<table><thead><tr>" +
    data.headers.map((h) => "<th>" + esc(h) + "</th>").join("") +
    "</tr></thead><tbody>" +
    data.rows.map((r) => "<tr>" +
      r.map((c) => `<td title="${esc(c)}">${esc(c)}</td>`).join("") + "</tr>").join("") +
    "</tbody></table>";
}

/* --- autocomplete: SQL keywords + table and column names --- */
let acItems = [], acIndex = 0, acWordStart = 0;

function acCandidates() {
  const names = [];
  if (state.schema) {
    for (const t of state.schema.tables) {
      names.push(t.name);
      for (const c of t.columns) names.push(c.name);
    }
  }
  return SQL_KEYWORDS.concat([...new Set(names)]);
}

$("sql-input").addEventListener("input", () => {
  const el = $("sql-input");
  const upto = el.value.slice(0, el.selectionStart);
  const m = upto.match(/[A-Za-z0-9_$]+$/);
  if (!m || m[0].length < 2) { hideAc(); return; }
  const word = m[0];
  acWordStart = el.selectionStart - word.length;
  const lower = word.toLowerCase();
  const seen = new Set();
  acItems = acCandidates().filter((c) => {
    const k = c.toLowerCase();
    if (!k.startsWith(lower) || k === lower || seen.has(k)) return false;
    seen.add(k);
    return true;
  }).slice(0, 8);
  if (!acItems.length) { hideAc(); return; }
  acIndex = 0;
  renderAc();
});

function renderAc() {
  const box = $("sql-ac");
  box.hidden = false;
  box.innerHTML = acItems.map((c, i) =>
    `<div class="sql-ac-item${i === acIndex ? " active" : ""}" data-i="${i}">${esc(c)}</div>`).join("");
}

function hideAc() { $("sql-ac").hidden = true; acItems = []; }

function acAccept(i) {
  const el = $("sql-input");
  const cand = acItems[i];
  const text = /^[A-Za-z_(*][A-Za-z0-9_()* ]*$/.test(cand) ? cand : quoteIdent(cand);
  el.value = el.value.slice(0, acWordStart) + text + el.value.slice(el.selectionStart);
  el.selectionStart = el.selectionEnd = acWordStart + text.length;
  hideAc();
  el.focus();
}

function acKeydown(e) {
  if ($("sql-ac").hidden || !acItems.length) return false;
  if (e.key === "ArrowDown") { acIndex = (acIndex + 1) % acItems.length; renderAc(); }
  else if (e.key === "ArrowUp") { acIndex = (acIndex + acItems.length - 1) % acItems.length; renderAc(); }
  else if (e.key === "Tab" || e.key === "Enter") { acAccept(acIndex); }
  else if (e.key === "Escape") { hideAc(); }
  else return false;
  e.preventDefault();
  return true;
}

$("sql-ac").addEventListener("mousedown", (e) => {
  const item = e.target.closest(".sql-ac-item");
  if (item) { e.preventDefault(); acAccept(+item.dataset.i); }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".sql-editor-wrap")) hideAc();
});

/* ---------- per-tool CLI help ---------- */
async function loadHelp() {
  if (state.helpLoaded) return;
  state.helpLoaded = true;
  const tool = state.tool;
  const data = await (await fetch("/api/tools/" + tool.id + "/help")).json();
  if (state.tool === tool) $("help-text").textContent = data.help || "No help output.";
}
$("help-details").addEventListener("toggle", () => {
  if ($("help-details").open) loadHelp();
});

loadTools();
