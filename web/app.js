/* Linkr frontend — no framework, no build step. Plain static files. */

const API = (window.LINKR_CONFIG && window.LINKR_CONFIG.apiBase) || "";

const form = document.getElementById("shorten-form");
const urlInput = document.getElementById("url");
const codeInput = document.getElementById("code");
const submitBtn = document.getElementById("submit");
const messageEl = document.getElementById("message");
const bodyEl = document.getElementById("links-body");
const statsEl = document.getElementById("stats");
const buildEl = document.getElementById("build");

function say(text, kind = "info") {
  messageEl.textContent = text;
  messageEl.className = `message ${kind}`;
  messageEl.hidden = !text;
}

async function api(path, options) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function row(link) {
  const tr = document.createElement("tr");

  const short = document.createElement("td");
  const a = document.createElement("a");
  a.href = link.short_url;
  a.textContent = link.code;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  short.append(a);

  const target = document.createElement("td");
  target.className = "target";
  target.title = link.target_url;
  target.textContent = link.target_url;

  const hits = document.createElement("td");
  hits.className = "num";
  hits.textContent = link.hits;

  const actions = document.createElement("td");
  actions.className = "num";
  const copy = document.createElement("button");
  copy.className = "ghost";
  copy.textContent = "copy";
  copy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(link.short_url);
    copy.textContent = "copied";
    setTimeout(() => (copy.textContent = "copy"), 1200);
  });
  const del = document.createElement("button");
  del.className = "ghost danger";
  del.textContent = "delete";
  del.addEventListener("click", async () => {
    try {
      await api(`/api/links/${encodeURIComponent(link.code)}`, { method: "DELETE" });
      await refresh();
    } catch (err) {
      say(err.message, "error");
    }
  });
  actions.append(copy, del);

  tr.append(short, target, hits, actions);
  return tr;
}

async function refresh() {
  try {
    const [links, stats] = await Promise.all([
      api("/api/links?limit=20"),
      api("/api/stats"),
    ]);

    bodyEl.replaceChildren();
    if (links.length === 0) {
      const tr = document.createElement("tr");
      tr.className = "empty";
      const td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = "No links yet.";
      tr.append(td);
      bodyEl.append(tr);
    } else {
      links.forEach((link) => bodyEl.append(row(link)));
    }

    statsEl.textContent = `${stats.total_links} links · ${stats.total_hits} hits`;
  } catch (err) {
    bodyEl.replaceChildren();
    const tr = document.createElement("tr");
    tr.className = "empty";
    const td = document.createElement("td");
    td.colSpan = 4;
    td.textContent = `Could not reach the API: ${err.message}`;
    tr.append(td);
    bodyEl.append(tr);
  }
}

async function showBuild() {
  try {
    const h = await api("/health");
    buildEl.textContent = `${h.env} · v${h.version} · ${h.git_sha.slice(0, 7)}`;
  } catch {
    buildEl.textContent = "api unreachable";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitBtn.disabled = true;
  say("");

  const payload = { url: urlInput.value.trim() };
  const code = codeInput.value.trim();
  if (code) payload.code = code;

  try {
    const link = await api("/api/links", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    say(`Created ${link.short_url}`, "success");
    form.reset();
    await refresh();
  } catch (err) {
    say(err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
});

refresh();
showBuild();
