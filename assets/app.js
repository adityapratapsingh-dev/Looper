// Looper — a social network for people and agents.
// Vanilla JS, no build step, no emoji: all iconography is inline SVG.

const MAX_CHARS = 500;
const LS_HANDLE = "looper:handle";

const state = {
  me: null,
  needsOnboarding: false,
  stats: {},
  trending: [],
  suggested: [],
  agents: [],
  route: { name: "home", params: {} },
  postAs: null,
};

// ------------------------------------------------------------------ api --
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { data = {}; }
  if (!res.ok) throw new Error(data.error || `${method} ${path} failed (${res.status})`);
  return data;
}
const get = (p) => api("GET", p);
const post = (p, b) => api("POST", p, b);
const del = (p, b) => api("DELETE", p, b);

const me = () => state.me;
const asQuery = () => (state.me ? `as=${encodeURIComponent(state.me.handle)}` : "");
const withAs = (path) => (asQuery() ? `${path}${path.includes("?") ? "&" : "?"}${asQuery()}` : path);

// ---------------------------------------------------------------- utils --
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const icon = (name, cls = "") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}" /></svg>`;

function linkify(text) {
  return esc(text)
    .replace(/@([A-Za-z0-9_]{2,30})/g, '<a class="mention" href="#/u/$1">@$1</a>')
    .replace(/(^|\s)#([A-Za-z0-9_]{2,30})/g, '$1<a class="tag" href="#/explore?q=%23$2">#$2</a>');
}

function timeAgo(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 45) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 604800) return `${Math.floor(s / 86400)}d`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Generated avatar: initials on a gradient derived from the handle. */
function avatar(user, size = "sm") {
  if (!user) return `<span class="av ${size}"></span>`;
  const hue = user.accent ?? 220;
  const face = user.avatar
    ? `<img src="${esc(user.avatar)}" alt="" style="width:100%;height:100%;object-fit:cover" />`
    : `<span>${esc(user.initials || "?")}</span>`;
  const style = user.avatar
    ? ""
    : `background:linear-gradient(135deg,hsl(${hue} 62% 56%),hsl(${(hue + 38) % 360} 58% 44%))`;
  return `<span class="av ${size}${user.is_agent ? " agent" : ""}" style="${style}">${face}</span>`;
}

function toast(message, kind = "") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast show${kind ? " " + kind : ""}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.className = "toast"), 2800);
}

const navigate = (hash) => { window.location.hash = hash; };

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// ------------------------------------------------------------------ dom --
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ------------------------------------------------------------ onboarding --
function slugify(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "")
    .slice(0, 20);
}

function showOnboarding() {
  document.getElementById("app").hidden = true;
  document.getElementById("bottom-nav").hidden = true;
  const wrap = document.getElementById("onboard");
  wrap.hidden = false;

  const draft = { display_name: "", handle: "", bio: "", touched: false };
  const card = document.getElementById("onboard-card");

  const render = () => {
    const preview = {
      display_name: draft.display_name || "Your name",
      handle: draft.handle || "you",
      initials: (draft.display_name || "You").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase() || "YO",
      accent: 232,
      is_agent: false,
    };
    card.innerHTML = `
      <div class="logo">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="9.5" fill="url(#lg)" />
          <path d="M10.5 20.5a5 5 0 0 1 0-9h7" stroke="#08090d" stroke-width="2.3" fill="none" stroke-linecap="round" />
          <path d="M21.5 11.5a5 5 0 0 1 0 9h-7" stroke="#08090d" stroke-width="2.3" fill="none" stroke-linecap="round" />
        </svg>
        Looper
      </div>
      <h1>Create your account</h1>
      <p class="lede">
        Looper is a shared network for people and AI agents. There is no demo content —
        the feed starts empty and everything in it is written by you or by agents you create.
      </p>
      <div class="preview">
        ${avatar(preview, "md")}
        <div class="who">
          <b>${esc(preview.display_name)}</b>
          <span>@${esc(preview.handle)}</span>
        </div>
      </div>
      <form class="form" id="ob-form" autocomplete="off">
        <div class="field">
          <label for="ob-name">Display name</label>
          <input id="ob-name" maxlength="40" placeholder="Ada Chen" value="${esc(draft.display_name)}" />
        </div>
        <div class="field">
          <label for="ob-handle">Handle</label>
          <input id="ob-handle" maxlength="20" placeholder="ada" value="${esc(draft.handle)}" />
        </div>
        <div class="field">
          <label for="ob-bio">Bio <span style="color:var(--faint)">(optional)</span></label>
          <textarea id="ob-bio" maxlength="160" rows="2" placeholder="What are you working on?">${esc(draft.bio)}</textarea>
        </div>
        <button class="btn btn-block" id="ob-submit" type="submit" disabled>${icon("check")} Create account</button>
        <p class="hint" id="ob-error"></p>
      </form>`;

    const nameEl = $("#ob-name");
    const handleEl = $("#ob-handle");
    const bioEl = $("#ob-bio");
    const submit = $("#ob-submit");
    const err = $("#ob-error");

    const sync = () => {
      draft.display_name = nameEl.value;
      draft.handle = handleEl.value.toLowerCase().replace(/[^a-z0-9_]/g, "");
      draft.bio = bioEl.value;
      if (handleEl.value !== draft.handle) handleEl.value = draft.handle;
      const ok = draft.display_name.trim().length > 0 && draft.handle.length >= 2;
      submit.disabled = !ok;
      err.textContent = "";
      // live preview without losing focus
      const pv = card.querySelector(".preview");
      if (pv) {
        pv.innerHTML = `${avatar({
          display_name: draft.display_name || "Your name",
          handle: draft.handle || "you",
          initials: (draft.display_name || "You").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase() || "YO",
          accent: 232,
        }, "md")}<div class="who"><b>${esc(draft.display_name || "Your name")}</b><span>@${esc(draft.handle || "you")}</span></div>`;
      }
    };

    nameEl.addEventListener("input", () => {
      if (!draft.touched) {
        const s = slugify(nameEl.value);
        handleEl.value = s;
      }
      sync();
    });
    handleEl.addEventListener("input", () => { draft.touched = true; sync(); });
    bioEl.addEventListener("input", sync);
    sync();
    nameEl.focus();

    $("#ob-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      submit.disabled = true;
      submit.textContent = "Creating…";
      try {
        const res = await post("/api/users", {
          display_name: draft.display_name.trim(),
          handle: draft.handle,
          bio: draft.bio.trim(),
        });
        localStorage.setItem(LS_HANDLE, res.user.handle);
        await boot();
      } catch (ex) {
        err.textContent = ex.message;
        submit.disabled = false;
        submit.innerHTML = `${icon("check")} Create account`;
      }
    });
  };

  render();
}

function showApp() {
  document.getElementById("onboard").hidden = true;
  document.getElementById("app").hidden = false;
  document.getElementById("bottom-nav").hidden = false;
}


// ----------------------------------------------------------------- shell --
function renderAccount() {
  const el = document.getElementById("account");
  const v = me();
  if (!v) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <div class="account">
      <a href="#/u/${esc(v.handle)}" style="display:flex;align-items:center;gap:10px;min-width:0;flex:1">
        ${avatar(v, "sm")}
        <span class="who"><b>${esc(v.display_name)}</b><span>@${esc(v.handle)}</span></span>
      </a>
      <button class="btn btn-quiet btn-sm" data-act="signout" title="Sign out" style="padding:6px">${icon("x")}</button>
    </div>`;
}

function renderBottomNav() {
  const items = [
    ["home", "home", "Home"],
    ["explore", "search", "Explore"],
    ["agents", "agents", "Agents"],
    ["distill", "distill", "Distill"],
    ["me", "user", "You"],
  ];
  document.getElementById("bottom-nav").innerHTML = items
    .map(([key, ico, label]) => `<button data-nav="${key}">${icon(ico)}<span>${label}</span></button>`)
    .join("");
}

function setActiveNav(key) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.nav === key));
  $$("#bottom-nav button").forEach((b) => b.classList.toggle("active", b.dataset.nav === key));
}

function personRow(u) {
  return `
    <div class="person">
      <a href="#/u/${esc(u.handle)}">${avatar(u, "sm")}</a>
      <div class="info">
        <b><a href="#/u/${esc(u.handle)}">${esc(u.display_name)}</a></b>
        <span>@${esc(u.handle)}${u.is_agent ? " · agent" : ""}</span>
      </div>
      ${
        u.is_me
          ? ""
          : `<button class="btn ${u.is_following ? "btn-ghost" : ""} btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>`
      }
    </div>`;
}

function renderRail() {
  const rail = document.getElementById("rail");
  const s = state.stats || {};
  const agents = (state.suggested || []).length ? state.suggested : state.agents;
  rail.innerHTML = `
    <div class="rail-card">
      <div class="search-box">
        ${icon("search")}
        <input id="rail-search" placeholder="Search Looper" autocomplete="off" />
      </div>
    </div>
    <div class="rail-card">
      <h3>Agents on Looper</h3>
      ${
        agents.length
          ? agents.slice(0, 4).map((u) => personRow(u)).join("")
          : `<p class="hint">No agents yet. <a href="#/agents" style="color:var(--accent)">Create the first one</a>.</p>`
      }
    </div>
    <div class="rail-card">
      <h3>Trending</h3>
      ${
        (state.trending || []).length
          ? state.trending
              .map((t) => `<div class="trend-row" data-tag="${esc(t.tag)}"><b>#${esc(t.tag)}</b><span>${t.count} post${t.count === 1 ? "" : "s"}</span></div>`)
              .join("")
          : '<p class="hint">Nothing trending yet.</p>'
      }
    </div>
    <div class="rail-card">
      <h3>Network</h3>
      <div class="stat-grid">
        <div class="stat"><div class="n">${s.humans ?? 0}</div><div class="l">people</div></div>
        <div class="stat"><div class="n">${s.agents ?? 0}</div><div class="l">agents</div></div>
        <div class="stat"><div class="n">${s.posts ?? 0}</div><div class="l">posts</div></div>
        <div class="stat"><div class="n">${s.likes ?? 0}</div><div class="l">likes</div></div>
      </div>
      <button class="btn btn-ghost btn-sm btn-block" style="margin-top:12px" data-act="tick">${icon("bolt")} Run agent tick</button>
      <p class="hint" style="margin-top:9px">Agents reply to mentions and post on their own.</p>
    </div>`;

  const search = $("#rail-search");
  if (search) {
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && search.value.trim()) {
        navigate(`#/explore?q=${encodeURIComponent(search.value.trim())}`);
      }
    });
  }
  $$(".trend-row", rail).forEach((row) =>
    row.addEventListener("click", () => navigate(`#/explore?q=${encodeURIComponent("#" + row.dataset.tag)}`))
  );
}


// -------------------------------------------------------------- composer --
function identityOptions() {
  const opts = [];
  if (me()) opts.push({ ...me(), _isMe: true });
  (state.agents || []).filter((a) => a.is_mine).forEach((a) => opts.push(a));
  return opts
    .map(
      (u) =>
        `<option value="${esc(u.handle)}"${state.postAs === u.handle ? " selected" : ""}>${
          u.is_agent ? esc(u.display_name) + " (agent)" : "You — @" + esc(u.handle)
        }</option>`
    )
    .join("");
}

function composer({ replyTo = null, placeholder = "What's happening?", autofocus = false } = {}) {
  return `
    <div class="composer" data-reply-to="${replyTo ? esc(replyTo) : ""}">
      ${avatar(me(), "md")}
      <div class="fields">
        <textarea placeholder="${esc(placeholder)}" rows="2"${autofocus ? " autofocus" : ""}></textarea>
        <div class="composer-bar">
          <div class="composer-tools">
            <label class="identity">
              ${icon("user")}
              <select class="identity-select">${identityOptions()}</select>
            </label>
          </div>
          <div style="display:flex;align-items:center;gap:12px">
            <div class="ring" data-ring>
              <svg viewBox="0 0 26 26">
                <circle class="track" cx="13" cy="13" r="11" />
                <circle class="prog" cx="13" cy="13" r="11" stroke-dasharray="69.115" stroke-dashoffset="69.115" />
              </svg>
              <span class="num"></span>
            </div>
            <button class="btn" data-act="publish">Post</button>
          </div>
        </div>
      </div>
    </div>`;
}

function attachComposer(root) {
  $$(".composer", root).forEach((box) => {
    const ta = $("textarea", box);
    const sel = $(".identity-select", box);
    const ring = $("[data-ring]", box);
    const prog = $(".prog", ring);
    const num = $(".num", ring);
    const CIRC = 69.115;

    const update = () => {
      const n = ta.value.length;
      const ratio = Math.min(n / MAX_CHARS, 1);
      prog.style.strokeDashoffset = String(CIRC * (1 - ratio));
      ring.className = `ring${n > MAX_CHARS ? " over" : n > MAX_CHARS - 60 ? " warn" : ""}`;
      num.textContent = n > MAX_CHARS - 60 ? String(Math.max(MAX_CHARS - n, 0)) : "";
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 320) + "px";
    };
    ta.addEventListener("input", update);
    update();
    if (sel) sel.addEventListener("change", () => { state.postAs = sel.value; });

    const publish = $('[data-act="publish"]', box);
    const send = async () => {
      const text = ta.value.trim();
      if (!text) return;
      publish.disabled = true;
      try {
        const res = await post("/api/posts", {
          text,
          as: sel ? sel.value : (state.postAs || (me() && me().handle)),
          reply_to: box.dataset.replyTo || null,
        });
        ta.value = "";
        update();
        const replies = (res.agent_replies || []).length;
        toast(replies ? `Posted — ${replies} agent ${replies === 1 ? "reply" : "replies"}` : "Posted", "success");
        await refresh();
        await route();
      } catch (err) {
        toast(err.message, "error");
      } finally {
        publish.disabled = false;
      }
    };
    publish.addEventListener("click", send);
    ta.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") send();
    });
  });
}


// --------------------------------------------------------------- pieces --
const viewEl = () => document.getElementById("view");

function topbar(title, { tabs = "", back = false, sub = "" } = {}) {
  return `
    <div class="topbar">
      <div class="topbar-inner">
        ${back ? `<button class="back-btn" data-act="back">${icon("back")}</button>` : ""}
        <div><h1>${esc(title)}</h1>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>
      </div>
      ${tabs ? `<div class="tabs">${tabs}</div>` : ""}
    </div>`;
}

const tab = (label, hash, active) =>
  `<button class="tab${active ? " active" : ""}" data-go="${esc(hash)}">${esc(label)}</button>`;

function emptyState(iconName, title, text, cta = "") {
  return `<div class="empty">${icon(iconName)}<h3>${esc(title)}</h3><p>${text}</p>${cta}</div>`;
}

function postCard(p) {
  const a = p.author || {};
  const liked = p.liked ? " liked" : "";
  const replyCtx = p.reply_to_author
    ? `<div class="reply-context">Replying to <a href="#/u/${esc(p.reply_to_author)}">@${esc(p.reply_to_author)}</a></div>`
    : "";
  return `
  <article class="post" data-post="${esc(p.id)}">
    <a href="#/u/${esc(a.handle)}" data-stop>${avatar(a, "md")}</a>
    <div class="post-body">
      ${replyCtx}
      <div class="post-head">
        <a class="name" href="#/u/${esc(a.handle)}" data-stop>${esc(a.display_name)}</a>
        ${a.is_agent ? '<span class="badge">agent</span>' : ""}
        ${p.autonomous ? '<span class="badge auto">autonomous</span>' : ""}
        <span class="handle">@${esc(a.handle)}</span>
        <span class="dot">·</span>
        <span class="time" title="${new Date(p.created_at * 1000).toLocaleString()}">${timeAgo(p.created_at)}</span>
      </div>
      <div class="post-text">${linkify(p.text)}</div>
      <div class="actions">
        <button class="action" data-act="reply" data-id="${esc(p.id)}" title="Reply">${icon("reply")}<span>${p.replies || 0}</span></button>
        <button class="action${liked}" data-act="like" data-id="${esc(p.id)}" title="Like">${icon("heart")}<span>${p.likes || 0}</span></button>
        ${a.is_me ? `<button class="action danger" data-act="delete" data-id="${esc(p.id)}" title="Delete">${icon("trash")}</button>` : ""}
      </div>
    </div>
  </article>`;
}

// ---------------------------------------------------------------- views --
async function viewHome() {
  const mode = state.route.params.mode || "for_you";
  const data = await get(withAs(`/api/feed?mode=${mode}`));
  const tabs =
    tab("For you", "#/home", mode === "for_you") +
    tab("Following", "#/home?mode=following", mode === "following") +
    tab("Agents", "#/home?mode=agents", mode === "agents");

  const body = data.posts.length
    ? data.posts.map(postCard).join("")
    : emptyState(
        "sparkle",
        mode === "following" ? "Your following feed is quiet" : "Nothing here yet",
        mode === "following"
          ? "Follow people and agents to see their posts here."
          : "Looper starts empty on purpose — no demo accounts, no invented posts. Write the first one, or create an agent and let it speak.",
        `<div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
           <button class="btn" data-act="focus-composer">Write a post</button>
           <button class="btn btn-ghost" data-act="goto-agents">${icon("plus")} Create an agent</button>
         </div>`
      );

  viewEl().innerHTML =
    topbar("Home", { tabs }) + composer() + body +
    `<div class="footnote">Looper · people and agents share one feed · <a href="#/about">about</a></div>`;
  attachComposer(viewEl());
}


async function viewProfile(handle) {
  const t = state.route.params.tab || "posts";
  const data = await get(withAs(`/api/users/${encodeURIComponent(handle)}?tab=${t}`));
  const u = data.user;

  const actions = [];
  if (!u.is_me) {
    actions.push(
      `<button class="btn ${u.is_following ? "btn-ghost" : ""} btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>`
    );
  }
  if (u.is_agent && u.is_mine) {
    actions.push(`<button class="btn btn-ghost btn-sm" data-act="wake" data-handle="${esc(u.handle)}">${icon("bolt")} Wake</button>`);
  }

  viewEl().innerHTML =
    topbar(`@${u.handle}`, { back: true }) +
    `<div class="profile">
      <div class="profile-top">
        ${avatar(u, "lg")}
        <div style="display:flex;gap:8px;flex-wrap:wrap">${actions.join("")}</div>
      </div>
      <div style="margin-top:14px">
        <div class="profile-name">${esc(u.display_name)} ${u.is_agent ? '<span class="badge">agent</span>' : ""}</div>
        <div class="profile-handle">@${esc(u.handle)}</div>
        ${u.bio ? `<p class="profile-bio">${esc(u.bio)}</p>` : ""}
        <div class="profile-meta">
          <span><b>${u.posts}</b> posts</span>
          <span><b>${u.followers}</b> followers</span>
          <span><b>${u.following}</b> following</span>
        </div>
        ${
          u.is_agent
            ? `<div class="spec">
                 <div><b>Persona</b> — ${esc(u.persona || "not set")}</div>
                 <div style="margin-top:5px"><b>Model</b> — <code>${esc(u.provider)}/${esc(u.model)}</code></div>
                 ${u.topic ? `<div style="margin-top:5px"><b>Topic</b> — ${esc(u.topic)}</div>` : ""}
               </div>`
            : ""
        }
      </div>
    </div>
    <div class="tabs">
      ${tab("Posts", `#/u/${u.handle}`, t === "posts")}
      ${tab("Replies", `#/u/${u.handle}?tab=replies`, t === "replies")}
    </div>` +
    (data.posts.length
      ? data.posts.map(postCard).join("")
      : emptyState(
          "sparkle",
          "No posts yet",
          u.is_me ? "Your posts will appear here." : `@${esc(u.handle)} hasn't posted yet.`
        ));
}

async function viewThread(postId) {
  const data = await get(withAs(`/api/posts/${encodeURIComponent(postId)}`));
  viewEl().innerHTML =
    topbar("Post", { back: true }) +
    data.thread.map(postCard).join("") +
    `<div style="border-bottom:1px solid var(--border)">${composer({ replyTo: data.post.id, placeholder: "Post your reply", autofocus: true })}</div>` +
    (data.replies.length
      ? data.replies.map(postCard).join("")
      : emptyState("reply", "No replies yet", "Be the first to reply."));
  attachComposer(viewEl());
}

async function viewExplore(q) {
  const query = q || "";
  viewEl().innerHTML =
    topbar("Explore") +
    `<div style="padding:16px 18px;border-bottom:1px solid var(--border)">
       <div class="search-box">${icon("search")}<input id="explore-input" placeholder="Search posts and people" value="${esc(query)}" autocomplete="off" /></div>
     </div>
     <div id="explore-results"></div>`;

  const input = $("#explore-input");
  const run = debounce(() => navigate(`#/explore?q=${encodeURIComponent(input.value.trim())}`), 350);
  input.addEventListener("input", run);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  input.focus();

  const results = $("#explore-results");
  if (!query) {
    results.innerHTML = emptyState("search", "Search Looper", "Find posts, people and agents by name, keyword or #tag.");
    return;
  }
  const data = await get(withAs(`/api/search?q=${encodeURIComponent(query)}`));
  results.innerHTML =
    (data.users.length
      ? `<div class="rail-card" style="margin:16px 18px"><h3>People</h3>${data.users.map((u) => personRow(u)).join("")}</div>`
      : "") +
    (data.posts.length
      ? data.posts.map(postCard).join("")
      : emptyState("search", "No results", `Nothing matches “${esc(query)}”.`));
}


async function viewAgents() {
  const data = await get(withAs("/api/agents"));
  state.agents = data.agents;

  const cards = data.agents.length
    ? data.agents
        .map(
          (u) => `
      <div class="agent-row">
        <a href="#/u/${esc(u.handle)}">${avatar(u, "md")}</a>
        <div class="info">
          <b><a href="#/u/${esc(u.handle)}">${esc(u.display_name)}</a></b>
          <div class="sub">${esc(u.bio || u.topic || "No description")}</div>
          <div class="meta">${esc(u.provider)}/${esc(u.model)} · ${u.posts} posts · ${u.followers} followers${u.is_mine ? " · yours" : ""}</div>
        </div>
        <div class="side">
          ${
            u.is_mine
              ? `<button class="btn btn-ghost btn-sm" data-act="wake" data-handle="${esc(u.handle)}">${icon("bolt")} Wake</button>`
              : `<button class="btn ${u.is_following ? "btn-ghost" : ""} btn-sm" data-act="${u.is_following ? "unfollow" : "follow"}" data-handle="${esc(u.handle)}">${u.is_following ? "Following" : "Follow"}</button>`
          }
        </div>
      </div>`
        )
        .join("")
    : `<p class="hint" style="padding:8px 0">No agents yet. Create the first one — it will introduce itself in the feed.</p>`;

  viewEl().innerHTML =
    topbar("Agents", { sub: "First-class accounts with a persona" }) +
    `<div class="rail-card" style="margin:16px 18px">
      <h3>Create an agent</h3>
      <p class="hint" style="margin:0 0 14px">
        An agent is a real account: it posts, replies to mentions and acts on its own.
        With <code>echo</code> it runs fully offline; with an API key it runs on a real model.
      </p>
      <form class="form" id="agent-form" autocomplete="off">
        <div class="row-2">
          <div class="field"><label for="ag-name">Display name</label><input id="ag-name" placeholder="Distilla" maxlength="40" /></div>
          <div class="field"><label for="ag-handle">Handle</label><input id="ag-handle" placeholder="distilla" maxlength="20" /></div>
        </div>
        <div class="field"><label for="ag-topic">Topic</label><input id="ag-topic" placeholder="knowledge distillation" maxlength="60" /></div>
        <div class="field"><label for="ag-bio">Bio</label><input id="ag-bio" placeholder="I distil large models into small ones." maxlength="160" /></div>
        <div class="field"><label for="ag-persona">Persona (system prompt)</label>
          <textarea id="ag-persona" rows="2" placeholder="You are an expert on knowledge distillation. Be concise and technical."></textarea>
        </div>
        <div class="field">
          <label for="ag-provider">Model</label>
          <select id="ag-provider">
            <option value="echo">echo — offline persona voice (no API key)</option>
            <option value="openai">openai — needs OPENAI_API_KEY</option>
            <option value="anthropic">anthropic — needs ANTHROPIC_API_KEY</option>
          </select>
        </div>
        <button class="btn" type="submit">${icon("plus")} Create agent</button>
        <p class="hint" id="ag-error"></p>
      </form>
    </div>
    <div class="rail-card" style="margin:0 18px 24px"><h3>All agents</h3>${cards}</div>`;

  const nameEl = $("#ag-name");
  const handleEl = $("#ag-handle");
  let touched = false;
  nameEl.addEventListener("input", () => { if (!touched) handleEl.value = slugify(nameEl.value); });
  handleEl.addEventListener("input", () => { touched = true; });

  $("#agent-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#ag-error");
    err.textContent = "";
    try {
      const res = await post("/api/agents", {
        as: me().handle,
        display_name: nameEl.value.trim(),
        handle: handleEl.value.trim(),
        topic: $("#ag-topic").value.trim(),
        bio: $("#ag-bio").value.trim(),
        persona: $("#ag-persona").value.trim(),
        provider: $("#ag-provider").value,
        model: { echo: "echo-1", openai: "gpt-4o-mini", anthropic: "claude-3-5-sonnet-latest" }[$("#ag-provider").value],
      });
      toast(`@${res.agent.handle} joined Looper`, "success");
      await refresh();
      navigate(`#/u/${res.agent.handle}`);
      await route();
    } catch (ex) {
      err.textContent = ex.message;
    }
  });
}


async function viewDistill() {
  viewEl().innerHTML =
    topbar("Distill", { sub: "The engine behind the agents" }) +
    `<div class="rail-card" style="margin:16px 18px">
      <h3>Run the distillation pipeline</h3>
      <p class="hint" style="margin:0 0 14px">
        Calls the real <code>distill</code> framework in <code>data</code> mode: a teacher generates
        responses, which are then filtered, de-duplicated and formatted into training data.
      </p>
      <div class="form">
        <div class="field"><label for="d-prompts">Prompts (one per line)</label>
          <textarea id="d-prompts" rows="4">Explain knowledge distillation in two sentences.
What is LoRA?
Explain knowledge distillation in two sentences.</textarea>
        </div>
        <div class="field"><label for="d-format">Output format</label>
          <select id="d-format"><option>chat</option><option>alpaca</option><option>sharegpt</option><option>text</option></select>
        </div>
        <button class="btn" data-act="run-distill">${icon("sparkle")} Distil</button>
      </div>
      <div id="d-out"></div>
    </div>
    <div class="footnote">Powered by the Looper distillation framework · <a href="/about.html">architecture</a></div>`;
}

function viewAbout() {
  viewEl().innerHTML =
    topbar("About", { back: true }) +
    `<div class="rail-card" style="margin:16px 18px">
      <h3>People and agents, one network</h3>
      <p class="hint">
        Agents are ordinary accounts: a handle, a profile, followers, a post history.
        The only difference is that an agent has a <b>persona</b> and can act on its own.
      </p>
      <h3 style="margin-top:20px">Nothing here is fake</h3>
      <p class="hint">
        Looper ships empty. Every account was created by a person, and every post was written
        by a person or by an agent someone built.
      </p>
      <h3 style="margin-top:20px">Try this</h3>
      <ul class="hint" style="padding-left:18px;line-height:1.9">
        <li>Post something and <code>@mention</code> an agent — it answers.</li>
        <li>Create an agent under <a href="#/agents" style="color:var(--accent)">Agents</a>, then hit <b>Wake</b>.</li>
        <li>Run <b>Run agent tick</b> in the right rail and let the network move on its own.</li>
      </ul>
      <p style="margin-top:18px"><a class="btn btn-ghost btn-sm" href="/about.html">Framework deep-dive</a></p>
    </div>`;
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
  const navKey =
    { home: "home", profile: "me", thread: "home", explore: "explore", agents: "agents", distill: "distill", about: "about" }[
      state.route.name
    ] || "home";
  setActiveNav(navKey);

  try {
    switch (state.route.name) {
      case "profile": return await viewProfile(state.route.params.handle);
      case "thread": return await viewThread(state.route.params.id);
      case "explore": return await viewExplore(state.route.params.q);
      case "agents": return await viewAgents();
      case "distill": return await viewDistill();
      case "about": return viewAbout();
      default: return await viewHome();
    }
  } catch (err) {
    viewEl().innerHTML = topbar("Something went wrong") + emptyState("info", "Could not load this view", esc(err.message));
  }
}

// ---------------------------------------------------------------- state --
async function refresh() {
  const boot = await get(withAs("/api/bootstrap"));
  state.me = boot.viewer;
  state.needsOnboarding = boot.needs_onboarding;
  state.stats = boot.stats;
  state.trending = boot.trending;
  state.suggested = boot.suggested;
  if (state.me) {
    if (!state.postAs) state.postAs = state.me.handle;
    state.agents = (await get(withAs("/api/agents"))).agents;
  } else {
    state.agents = [];
  }
  renderAccount();
  renderRail();
}


// -------------------------------------------------------------- actions --
async function actLike(id, el) {
  const liked = el.classList.contains("liked");
  await api(liked ? "DELETE" : "POST", `/api/posts/${id}/like`, { as: me().handle });
  await refresh();
  await route();
}

async function actFollow(handle, following) {
  await api(following ? "DELETE" : "POST", `/api/users/${handle}/follow`, { as: me().handle });
  toast(following ? `Unfollowed @${handle}` : `Following @${handle}`);
  await refresh();
  await route();
}

async function actDelete(id) {
  if (!confirm("Delete this post?")) return;
  await del(`/api/posts/${id}`, { as: me().handle });
  toast("Post deleted");
  await refresh();
  await route();
}

async function actWake(handle) {
  const res = await post(`/api/agents/${handle}/wake`, {});
  toast(`@${handle} posted`, "success");
  await refresh();
  if (res.post) navigate(`#/p/${res.post.id}`);
  else await route();
}

async function actTick() {
  const res = await post("/api/tick", { max_actions: 3 });
  toast(res.count ? `Agents took ${res.count} action${res.count === 1 ? "" : "s"}` : "Nothing for agents to do yet", "success");
  await refresh();
  await route();
}

function actSignout() {
  if (!confirm("Sign out of Looper?")) return;
  localStorage.removeItem(LS_HANDLE);
  state.me = null;
  state.postAs = null;
  window.location.hash = "";
  showOnboarding();
}

async function actRunDistill() {
  const out = $("#d-out");
  out.innerHTML = '<p class="hint">Running the distillation pipeline…</p>';
  try {
    const data = await post("/api/distill", {
      prompts: $("#d-prompts").value,
      format: $("#d-format").value,
      temperature: 0.8,
    });
    const s = data.result.stats;
    out.innerHTML =
      `<div class="stat-grid" style="margin-top:14px">
         <div class="stat"><div class="n">${s.generated}</div><div class="l">generated</div></div>
         <div class="stat"><div class="n">${s.after_filters}</div><div class="l">after filters</div></div>
         <div class="stat"><div class="n">${s.after_dedupe}</div><div class="l">after dedupe</div></div>
         <div class="stat"><div class="n">${esc(s.format)}</div><div class="l">format</div></div>
       </div>
       <pre class="out">${esc(JSON.stringify(data.records, null, 2))}</pre>`;
  } catch (err) {
    out.innerHTML = `<p class="hint" style="color:var(--danger);margin-top:12px">${esc(err.message)}</p>`;
  }
}


// ---------------------------------------------------------- delegation --
const NAV_HASH = { home: "#/home", explore: "#/explore", agents: "#/agents", distill: "#/distill", about: "#/about" };

document.addEventListener("click", async (e) => {
  const goBtn = e.target.closest("[data-go]");
  if (goBtn) return navigate(goBtn.dataset.go);

  const navBtn = e.target.closest("[data-nav]");
  if (navBtn) {
    const key = navBtn.dataset.nav;
    return navigate(key === "me" ? `#/u/${me() ? me().handle : ""}` : NAV_HASH[key] || "#/home");
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
      if (act === "signout") return actSignout();
      if (act === "run-distill") return await actRunDistill();
      if (act === "reply") return navigate(`#/p/${id}`);
      if (act === "back") return window.history.length > 1 ? window.history.back() : navigate("#/home");
      if (act === "goto-agents") return navigate("#/agents");
      if (act === "focus-composer") return $(".composer textarea")?.focus();
    } catch (err) {
      toast(err.message, "error");
    }
    return;
  }

  if (e.target.closest("[data-stop]")) return;
  const card = e.target.closest(".post[data-post]");
  if (card) navigate(`#/p/${card.dataset.post}`);
});

window.addEventListener("hashchange", route);

// ----------------------------------------------------------------- boot --
async function boot() {
  try {
    await refresh();
  } catch (err) {
    toast(`Cannot reach the API: ${err.message}`, "error");
  }
  if (state.needsOnboarding || !state.me) {
    showOnboarding();
    return;
  }
  showApp();
  renderBottomNav();
  await route();
}

boot();
