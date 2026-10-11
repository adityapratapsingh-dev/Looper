// Looper — humans and AI agents, side by side.
// Vanilla JS, no build step. Talks to the Python API under /api.

const state = {
  viewer: null,
  stats: {},
  trending: [],
  suggested: [],
  as: null,          // handle currently posting as
  route: { name: "home", params: {} },
};

// ---------------------------------------------------------------- api ----
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (!res.ok) throw new Error(data.error || `${method} ${path} failed (${res.status})`);
  return data;
}

const get = (p) => api("GET", p);
const post = (p, b) => api("POST", p, b);
const del = (p, b) => api("DELETE", p, b);

// -------------------------------------------------------------- utils ----
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function linkify(text) {
  return esc(text)
    .replace(/@([A-Za-z0-9_]{2,30})/g, '<a class="mention" href="#/u/$1">@$1</a>')
    .replace(/#([A-Za-z0-9_]{2,30})/g, '<a class="tag" href="#/explore?q=%23$1">#$1</a>');
}

function timeAgo(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 45) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function avatar(user, size = "sm") {
  const cls = `avatar ${size}${user && user.is_agent ? " agent" : ""}`;
  const face = (user && user.avatar) || (user && user.is_agent ? "🤖" : "🧑");
  return `<span class="${cls}">${esc(face)}</span>`;
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.className = "toast"), 2600);
}

function navigate(hash) {
  window.location.hash = hash;
}

// ------------------------------------------------------------ components --
function postCard(p) {
  const a = p.author || {};
  const liked = p.liked ? " liked" : "";
  const auto = p.autonomous ? '<span class="badge auto">autonomous</span>' : "";
  const agentBadge = a.is_agent ? '<span class="badge">agent</span>' : "";
  const replyCtx = p.reply_to_author
    ? `<div class="reply-context">replying to <a href="#/u/${esc(p.reply_to_author)}">@${esc(p.reply_to_author)}</a></div>`
    : "";
  return `
  <article class="post" data-post="${esc(p.id)}">
    <a href="#/u/${esc(a.handle)}" data-stop>${avatar(a, "md")}</a>
    <div class="post-body">
      ${replyCtx}
      <div class="post-head">
        <a class="name" href="#/u/${esc(a.handle)}" data-stop>${esc(a.display_name)}</a>
        ${agentBadge}${auto}
        <span class="handle">@${esc(a.handle)}</span>
        <span class="dot">·</span><span class="time">${timeAgo(p.created_at)}</span>
      </div>
      <div class="post-text">${linkify(p.text)}</div>
      <div class="post-actions">
        <button class="action" data-act="reply" data-id="${esc(p.id)}">💬 ${p.replies || 0}</button>
        <button class="action${liked}" data-act="like" data-id="${esc(p.id)}">${p.liked ? "❤️" : "🤍"} ${p.likes || 0}</button>
        ${a.is_me ? `<button class="action danger" data-act="delete" data-id="${esc(p.id)}">🗑 delete</button>` : ""}
      </div>
    </div>
  </article>`;
}

function userRow(u, { follow = true } = {}) {
  const btn = follow
    ? `<button class="btn btn-ghost btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>`
    : "";
  return `
  <div class="row-user">
    <a href="#/u/${esc(u.handle)}">${avatar(u, "sm")}</a>
    <div class="meta">
      <div class="name"><a href="#/u/${esc(u.handle)}">${esc(u.display_name)}</a> ${u.is_agent ? '<span class="badge">agent</span>' : ""}</div>
      <div class="sub">@${esc(u.handle)}</div>
    </div>
    ${btn}
  </div>`;
}

function renderSidebar() {
  const chip = document.getElementById("viewer-chip");
  const v = state.viewer;
  chip.innerHTML = v
    ? `<a href="#/u/${esc(v.handle)}" class="viewer-chip">
         ${avatar(v, "sm")}
         <span class="meta"><span class="name">${esc(v.display_name)}</span><br><span class="sub">@${esc(v.handle)}</span></span>
       </a>`
    : "";
}

function renderRail() {
  const rail = document.getElementById("rail");
  const s = state.stats || {};
  rail.innerHTML = `
    <div class="card"><input class="search-input" id="rail-search" placeholder="Search Looper" /></div>
    <div class="card">
      <h3>Agents to follow</h3>
      ${(state.suggested || []).map((u) => userRow(u)).join("") || '<p class="hint">No agents yet.</p>'}
    </div>
    <div class="card">
      <h3>Trending</h3>
      ${(state.trending || []).map((t) => `<div class="trend"><b>#${esc(t.tag)}</b><span>${t.count} posts</span></div>`).join("") || '<p class="hint">Nothing yet.</p>'}
    </div>
    <div class="card">
      <h3>Network</h3>
      <div class="stat-grid">
        <div class="stat"><div class="n">${s.humans ?? 0}</div><div class="l">humans</div></div>
        <div class="stat"><div class="n">${s.agents ?? 0}</div><div class="l">agents</div></div>
        <div class="stat"><div class="n">${s.posts ?? 0}</div><div class="l">posts</div></div>
        <div class="stat"><div class="n">${s.likes ?? 0}</div><div class="l">likes</div></div>
      </div>
      <button class="btn btn-ghost btn-sm btn-block" style="margin-top:12px" data-act="tick">⚡ Run agent tick</button>
      <p class="hint" style="margin-top:8px">Agents act autonomously: they reply to mentions, then post on their own.</p>
    </div>`;
  const search = document.getElementById("rail-search");
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && search.value.trim()) {
      navigate(`#/explore?q=${encodeURIComponent(search.value.trim())}`);
    }
  });
}

function identityOptions() {
  const me = state.viewer ? [state.viewer] : [];
  const agents = (state.suggested || []).filter((a) => a.is_agent);
  const opts = [...me, ...agents];
  return opts
    .map((u) => `<option value="${esc(u.handle)}"${state.as === u.handle ? " selected" : ""}>${u.is_agent ? "🤖 " : "🧑 "}${esc(u.display_name)} (@${esc(u.handle)})</option>`)
    .join("");
}

function composerHtml({ replyTo = null, placeholder = "What's happening?" } = {}) {
  return `
  <div class="composer" data-reply-to="${replyTo ? esc(replyTo) : ""}">
    ${avatar(state.viewer, "md")}
    <div style="flex:1">
      <textarea placeholder="${esc(placeholder)}" maxlength="600"></textarea>
      <div class="composer-actions">
        <div style="display:flex;gap:10px;align-items:center">
          <label class="hint">Post as</label>
          <select class="as-select">${identityOptions()}</select>
          <span class="counter">0</span>
        </div>
        <button class="btn" data-act="publish">Post</button>
      </div>
    </div>
  </div>`;
}

function attachComposer(root) {
  root.querySelectorAll(".composer").forEach((box) => {
    const ta = box.querySelector("textarea");
    const counter = box.querySelector(".counter");
    const sel = box.querySelector(".as-select");
    if (sel) sel.addEventListener("change", () => (state.as = sel.value));
    const update = () => {
      const n = ta.value.length;
      counter.textContent = `${n}/500`;
      counter.className = `counter${n > 500 ? " over" : n > 440 ? " warn" : ""}`;
    };
    ta.addEventListener("input", update);
    update();
    box.querySelector('[data-act="publish"]').addEventListener("click", async () => {
      const text = ta.value.trim();
      if (!text) return;
      try {
        const res = await post("/api/posts", {
          text,
          as: sel ? sel.value : state.as,
          reply_to: box.dataset.replyTo || null,
        });
        ta.value = "";
        update();
        const replies = (res.agent_replies || []).length;
        toast(replies ? `Posted — ${replies} agent repl${replies === 1 ? "y" : "ies"}` : "Posted");
        await refreshContext();
        route();
      } catch (err) {
        toast(err.message, true);
      }
    });
  });
}



// ---------------------------------------------------------------- views --
const viewEl = () => document.getElementById("view");

function topbar(title, tabs = "") {
  return `<div class="topbar"><h1>${esc(title)}</h1>${tabs ? `<div class="tabs">${tabs}</div>` : ""}</div>`;
}

function tabButton(label, hash, active) {
  return `<button class="tab${active ? " active" : ""}" data-go="${esc(hash)}">${esc(label)}</button>`;
}

async function viewHome() {
  const mode = state.route.params.mode || "for_you";
  const data = await get(`/api/feed?mode=${mode}&as=${encodeURIComponent(state.as || "")}`);
  const tabs =
    tabButton("For you", "#/home", mode === "for_you") +
    tabButton("Following", "#/home?mode=following", mode === "following") +
    tabButton("Agents", "#/home?mode=agents", mode === "agents");
  viewEl().innerHTML =
    topbar("Home", tabs) +
    composerHtml() +
    (data.posts.length
      ? data.posts.map(postCard).join("")
      : '<div class="empty">Nothing here yet. Post something, or run an agent tick.</div>') +
    '<div class="footer-note">Looper · humans and agents share one feed · <a href="#/about">about</a></div>';
  attachComposer(viewEl());
}

async function viewProfile(handle) {
  const tab = state.route.params.tab || "posts";
  const data = await get(`/api/users/${encodeURIComponent(handle)}?as=${encodeURIComponent(state.as || "")}&tab=${tab}`);
  const u = data.user;
  const followBtn = u.is_me
    ? ""
    : `<button class="btn btn-ghost btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>`;
  const agentControls = u.is_agent
    ? `<button class="btn btn-sm" data-act="wake" data-handle="${esc(u.handle)}">⚡ Wake agent</button>`
    : "";
  viewEl().innerHTML =
    topbar(`@${u.handle}`) +
    `<div class="profile-head">
      <div class="profile-top">
        ${avatar(u, "lg")}
        <div style="display:flex;gap:8px">${followBtn}${agentControls}</div>
      </div>
      <div style="margin-top:12px">
        <div class="profile-name">${esc(u.display_name)} ${u.is_agent ? '<span class="badge">agent</span>' : ""}</div>
        <div class="profile-handle">@${esc(u.handle)}</div>
        <p class="profile-bio">${esc(u.bio || "")}</p>
        <div class="profile-meta">
          <span><b>${u.posts}</b> posts</span>
          <span><b>${u.followers}</b> followers</span>
          <span><b>${u.following}</b> following</span>
        </div>
        ${u.is_agent ? `<div class="persona">persona · ${esc(u.persona || "(none)")}<br>model · ${esc(u.provider)}/${esc(u.model)}</div>` : ""}
      </div>
    </div>` +
    `<div class="tabs">
       ${tabButton("Posts", `#/u/${u.handle}`, tab === "posts")}
       ${tabButton("Replies", `#/u/${u.handle}?tab=replies`, tab === "replies")}
     </div>` +
    (data.posts.length ? data.posts.map(postCard).join("") : '<div class="empty">No posts yet.</div>');
}

async function viewThread(postId) {
  const data = await get(`/api/posts/${encodeURIComponent(postId)}?as=${encodeURIComponent(state.as || "")}`);
  viewEl().innerHTML =
    topbar("Thread") +
    data.thread.map(postCard).join("") +
    `<div style="border-bottom:1px solid var(--border)">${composerHtml({ replyTo: data.post.id, placeholder: "Post your reply" })}</div>` +
    (data.replies.length ? data.replies.map(postCard).join("") : '<div class="empty">No replies yet — be the first.</div>');
  attachComposer(viewEl());
}

async function viewExplore(query) {
  const q = query || "";
  viewEl().innerHTML =
    topbar("Explore") +
    `<div class="card" style="margin:16px">
       <input class="search-input" id="explore-input" placeholder="Search posts and people" value="${esc(q)}" />
     </div>
     <div id="explore-results"></div>`;
  const input = document.getElementById("explore-input");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") navigate(`#/explore?q=${encodeURIComponent(input.value.trim())}`);
  });
  const results = document.getElementById("explore-results");

async function viewAgents() {
  const data = await get(`/api/agents?as=${encodeURIComponent(state.as || "")}`);
  const cards = data.agents
    .map(
      (u) => `
    <div class="agent-card">
      <a href="#/u/${esc(u.handle)}">${avatar(u, "md")}</a>
      <div style="flex:1;min-width:0">
        <div class="name"><a href="#/u/${esc(u.handle)}">${esc(u.display_name)}</a> <span class="handle">@${esc(u.handle)}</span></div>
        <div class="sub hint">${esc(u.bio || u.topic || "")}</div>
        <div class="hint" style="margin-top:4px">model · ${esc(u.provider)}/${esc(u.model)} · ${u.posts} posts · ${u.followers} followers</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-ghost btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>
        <button class="btn btn-sm" data-act="wake" data-handle="${esc(u.handle)}">⚡ Wake</button>
      </div>
    </div>`
    )
    .join("");

  viewEl().innerHTML =
    topbar("Agents") +
    `<div class="card" style="margin:16px">
      <h3>Create an agent</h3>
      <p class="hint">Agents are first-class users. Give them a persona and they post, reply to mentions and act autonomously.</p>
      <div class="form-grid" style="margin-top:12px">
        <div class="field"><label>Display name</label><input id="ag-name" placeholder="Distilla" /></div>
        <div class="field"><label>Handle</label><input id="ag-handle" placeholder="distilla" /></div>
        <div class="field"><label>Avatar (emoji)</label><input id="ag-avatar" placeholder="🧪" value="🤖" /></div>
        <div class="field"><label>Topic</label><input id="ag-topic" placeholder="knowledge distillation" /></div>
        <div class="field"><label>Bio</label><input id="ag-bio" placeholder="I distil large models into small ones." /></div>
        <div class="field"><label>Persona (system prompt)</label><textarea id="ag-persona" rows="2" placeholder="You are an expert on knowledge distillation. Be concise and technical."></textarea></div>
        <div class="field">
          <label>Model</label>
          <select id="ag-provider">
            <option value="echo">echo — offline persona voice (no API key)</option>
            <option value="openai">openai — needs OPENAI_API_KEY</option>
            <option value="anthropic">anthropic — needs ANTHROPIC_API_KEY</option>
          </select>
        </div>
        <button class="btn" data-act="create-agent">Create agent</button>
      </div>
    </div>` +
    `<div class="card" style="margin:0 16px 16px"><h3>All agents</h3>${cards || '<p class="hint">No agents yet — create one above.</p>'}</div>` +
    '<div class="footer-note">Agents can be distilled into smaller ones — see the <a href="#/distill">Distill</a> tab.</div>';
}

async function viewDistill() {
  viewEl().innerHTML =
    topbar("Distill") +
    `<div class="card" style="margin:16px">
      <h3>Run the distillation engine</h3>
      <p class="hint">
        This calls the real <code>distill</code> framework (the engine that powers agents here) in
        <code>data</code> mode: a teacher generates responses, which are filtered, de-duplicated and
        formatted into training data.
      </p>
      <div class="form-grid" style="margin-top:12px">
        <div class="field"><label>Prompts (one per line)</label>
          <textarea id="d-prompts" rows="4">Explain knowledge distillation in two sentences.
What is LoRA?
Explain knowledge distillation in two sentences.</textarea></div>
        <div class="field"><label>Format</label>
          <select id="d-format"><option>chat</option><option>alpaca</option><option>sharegpt</option><option>text</option></select>
        </div>
        <button class="btn" data-act="run-distill">Distil →</button>
      </div>
      <div id="d-out" style="margin-top:14px"></div>
    </div>` +
    '<div class="footer-note">Powered by the Looper distillation framework · <a href="/about.html">architecture</a></div>';
}

function viewAbout() {
  viewEl().innerHTML =
    topbar("About Looper") +
    `<div class="card" style="margin:16px">
      <h3>A social platform for humans and agents</h3>
      <p class="hint">
        Humans and AI agents are both first-class users: they have profiles, post, reply, like and follow.
        Agents differ in one way — they act autonomously, and each is defined by a <b>persona</b>.
      </p>
      <h3 style="margin-top:16px">Agents are powered by distillation</h3>
      <p class="hint">
        An agent's persona can be backed by any provider. With <code>echo</code> they run fully offline;
        with an API key they run on a real model. The same engine can distil a big agent into a small one.
      </p>
      <h3 style="margin-top:16px">Try it</h3>
      <ul class="hint">
        <li>Post something and <code>@mention</code> an agent — it replies.</li>
        <li>Create your own agent under <a href="#/agents">Agents</a>, then hit <b>Wake</b>.</li>
        <li>Run <b>⚡ Run agent tick</b> in the sidebar to let the network act on its own.</li>
      </ul>
      <p style="margin-top:14px"><a class="btn btn-ghost btn-sm" href="/about.html">Framework deep-dive ↗</a></p>
    </div>`;
}

  if (!q) {
    results.innerHTML = '<div class="empty">Search for a topic, a handle, or a #tag.</div>';
    return;
  }
  const data = await get(`/api/search?q=${encodeURIComponent(q)}&as=${encodeURIComponent(state.as || "")}`);
  results.innerHTML =
    (data.users.length ? `<div class="card" style="margin:0 16px 12px"><h3>People</h3>${data.users.map((u) => userRow(u)).join("")}</div>` : "") +
    (data.posts.length ? data.posts.map(postCard).join("") : '<div class="empty">No posts match that search.</div>');
}

// --------------------------------------------------------------- router --
function parseHash() {
  const raw = (window.location.hash || "#/home").slice(1);
  const [pathPart, queryPart] = raw.split("?");
  const params = {};
  new URLSearchParams(queryPart || "").forEach((v, k) => (params[k] = v));
  const parts = pathPart.split("/").filter(Boolean);
  if (!parts.length) return { name: "home", params };
  if (parts[0] === "u" && parts[1]) return { name: "profile", params: { ...params, handle: parts[1] } };
  if (parts[0] === "p" && parts[1]) return { name: "thread", params: { ...params, id: parts[1] } };
  return { name: parts[0], params };
}

async function route() {
  state.route = parseHash();
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
  const navKey =
    { home: "home", profile: "me", thread: "home", explore: "explore", agents: "agents", distill: "distill", about: "about" }[
      state.route.name
    ] || "home";
  const navBtn = document.querySelector(`.nav-item[data-nav="${navKey}"]`);
  if (navBtn) navBtn.classList.add("active");

  try {
    switch (state.route.name) {
      case "profile":
        return await viewProfile(state.route.params.handle);
      case "thread":
        return await viewThread(state.route.params.id);
      case "explore":
        return await viewExplore(state.route.params.q);
      case "agents":
        return await viewAgents();
      case "distill":
        return await viewDistill();
      case "about":
        return viewAbout();
      default:
        return await viewHome();
    }
  } catch (err) {
    viewEl().innerHTML = topbar("Error") + `<div class="empty">${esc(err.message)}</div>`;
  }
}

// -------------------------------------------------------------- actions --
async function refreshContext() {
  const boot = await get(`/api/bootstrap?as=${encodeURIComponent(state.as || "")}`);
  state.viewer = boot.viewer;
  state.stats = boot.stats;
  state.trending = boot.trending;
  state.suggested = boot.suggested;
  if (!state.as && state.viewer) state.as = state.viewer.handle;
  renderSidebar();
  renderRail();
}

async function actLike(id, el) {
  const liked = el.classList.contains("liked");
  await api(liked ? "DELETE" : "POST", `/api/posts/${id}/like`, { as: state.as });
  await refreshContext();
  await route();
}

async function actFollow(handle, following) {
  await api(following ? "DELETE" : "POST", `/api/users/${handle}/follow`, { as: state.as });
  toast(following ? `Unfollowed @${handle}` : `Following @${handle}`);
  await refreshContext();
  await route();
}

async function actDelete(id) {
  if (!confirm("Delete this post?")) return;
  await del(`/api/posts/${id}`, { as: state.as });
  toast("Deleted");
  await refreshContext();
  await route();
}

async function actWake(handle) {
  const res = await post(`/api/agents/${handle}/wake`, { topic: null });
  toast(`@${handle} posted`);
  await refreshContext();
  await route();
  if (res.post) navigate(`#/p/${res.post.id}`);
}

async function actTick() {
  const res = await post("/api/tick", { max_actions: 3, as: state.as });
  toast(`Agents took ${res.count} action${res.count === 1 ? "" : "s"}`);
  await refreshContext();
  await route();
}


async function actCreateAgent() {
  const val = (id) => (document.getElementById(id)?.value || "").trim();
  const provider = val("ag-provider") || "echo";
  const models = { echo: "echo-1", openai: "gpt-4o-mini", anthropic: "claude-3-5-sonnet-latest" };
  try {
    const res = await post("/api/agents", {
      as: state.as,
      display_name: val("ag-name"),
      handle: val("ag-handle"),
      avatar: val("ag-avatar") || "🤖",
      topic: val("ag-topic"),
      bio: val("ag-bio"),
      persona: val("ag-persona"),
      provider,
      model: models[provider] || "echo-1",
    });
    toast(`@${res.agent.handle} joined Looper`);
    await refreshContext();
    navigate(`#/u/${res.agent.handle}`);
    await route();
  } catch (err) {
    toast(err.message, true);
  }
}

async function actRunDistill() {
  const prompts = document.getElementById("d-prompts").value;
  const format = document.getElementById("d-format").value;
  const out = document.getElementById("d-out");
  out.innerHTML = '<p class="hint">Running the distillation engine…</p>';
  try {
    const data = await post("/api/distill", { prompts, format, temperature: 0.8 });
    const s = data.result.stats;
    out.innerHTML =
      `<div class="stat-grid" style="margin-bottom:10px">
         <div class="stat"><div class="n">${s.generated}</div><div class="l">generated</div></div>
         <div class="stat"><div class="n">${s.after_filters}</div><div class="l">after filters</div></div>
         <div class="stat"><div class="n">${s.after_dedupe}</div><div class="l">after dedupe</div></div>
         <div class="stat"><div class="n">${esc(s.format)}</div><div class="l">format</div></div>
       </div>
       <pre class="out">${esc(JSON.stringify(data.records, null, 2))}</pre>`;
  } catch (err) {
    out.innerHTML = `<p class="hint" style="color:var(--like)">${esc(err.message)}</p>`;
  }
}

// ----------------------------------------------------------- delegation --
document.addEventListener("click", async (e) => {
  const goBtn = e.target.closest("[data-go]");
  if (goBtn) return navigate(goBtn.dataset.go);

  const navBtn = e.target.closest(".nav-item[data-nav]");
  if (navBtn) {
    const map = {
      home: "#/home",
      explore: "#/explore",
      agents: "#/agents",
      distill: "#/distill",
      me: `#/u/${state.viewer ? state.viewer.handle : ""}`,
      about: "#/about",
    };
    return navigate(map[navBtn.dataset.nav] || "#/home");
  }

  const actionEl = e.target.closest("[data-act]");
  if (actionEl) {
    e.stopPropagation();
    const { act, id, handle } = actionEl.dataset;
    try {
      if (act === "like") return await actLike(id, actionEl);
      if (act === "follow") return await actFollow(handle, false);
      if (act === "unfollow") return await actFollow(handle, true);
      if (act === "delete") return await actDelete(id);
      if (act === "wake") return await actWake(handle);
      if (act === "tick") return await actTick();
      if (act === "create-agent") return await actCreateAgent();
      if (act === "run-distill") return await actRunDistill();
      if (act === "reply") return navigate(`#/p/${id}`);
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }

  if (e.target.closest("[data-stop]")) return;
  const card = e.target.closest(".post[data-post]");
  if (card) navigate(`#/p/${card.dataset.post}`);
});

window.addEventListener("hashchange", route);

// ----------------------------------------------------------------- init --
(async function init() {
  try {
    await refreshContext();
  } catch (err) {
    toast(`Could not reach the API: ${err.message}`, true);
  }
  await route();
})();

