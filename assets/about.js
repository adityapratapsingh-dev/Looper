// Looper playground — calls the real Python `data` mode via /api.
// Falls back to a small client-side simulation when the API is unavailable
// (e.g. the page is opened as a static file).

const $ = (id) => document.getElementById(id);
let lastResult = null;
let activeTab = "pretty";

const els = {
  prompts: $("prompts"),
  format: $("format"),
  temperature: $("temperature"),
  tempOut: $("temp-out"),
  run: $("run"),
  stats: $("stats"),
  out: $("out"),
  note: $("api-note"),
  version: $("version-pill"),
};

els.temperature.addEventListener("input", () => {
  els.tempOut.textContent = Number(els.temperature.value).toFixed(1);
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    activeTab = tab.dataset.tab;
    render();
  });
});

function chip(label, value) {
  return `<span class="chip">${label}: <b>${value}</b></span>`;
}

function renderStats(stats) {
  els.stats.innerHTML = [
    chip("generated", stats.generated),
    chip("after filters", stats.after_filters),
    chip("after dedupe", stats.after_dedupe),
    chip("format", stats.format),
  ].join("");
}

function render() {
  if (!lastResult) return;
  const { records } = lastResult;
  els.out.textContent =
    activeTab === "json" ? JSON.stringify(records, null, 2) : prettyRecords(records);
}

function prettyRecords(records) {
  return records
    .map((rec, i) => {
      if (rec.messages) {
        const body = rec.messages
          .map((m) => `  ${m.role.padEnd(9)} ${m.content}`)
          .join("\n");
        return `#${i + 1}\n${body}`;
      }
      if (rec.instruction !== undefined) {
        return `#${i + 1}\n  instruction ${rec.instruction}\n  output      ${rec.output}`;
      }
      if (rec.conversations) {
        return `#${i + 1}\n` + rec.conversations.map((c) => `  ${c.from.padEnd(6)} ${c.value}`).join("\n");
      }
      return `#${i + 1}\n  ${rec.text}`;
    })
    .join("\n\n");
}

async function loadCatalogue() {
  try {
    const res = await fetch("/api");
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    els.version.textContent = `distillation framework · v${data.version} · ${data.modes.length} modes`;
    els.note.textContent = `API online — modes: ${data.modes.join(", ")} · providers: ${data.providers.join(", ")}`;
  } catch {
    els.note.textContent =
      "API offline — showing a client-side simulation of the same pipeline (the deployed version runs the real Python framework).";
  }
}

async function run() {
  els.run.disabled = true;
  els.run.textContent = "Distilling…";
  const payload = {
    prompts: els.prompts.value,
    format: els.format.value,
    temperature: Number(els.temperature.value),
  };
  try {
    const res = await fetch("/api", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "request failed");
    lastResult = data;
    renderStats(data.result.stats);
    render();
  } catch (err) {
    lastResult = simulate(payload);
    renderStats(lastResult.result.stats);
    render();
    els.note.textContent = `API unavailable (${err.message}); showing client-side simulation.`;
  } finally {
    els.run.disabled = false;
    els.run.textContent = "Distil →";
  }
}

// --- minimal client-side mirror of the data-mode pipeline -------------------
function simulate(payload) {
  const prompts = payload.prompts
    .split("\n")
    .map((p) => p.trim())
    .filter(Boolean);
  const templates = [
    (p) => `Based on the input, the answer is: ${p}`,
    (p) => `Here is a concise response to '${p}'.`,
    (p) => `Reasoning step 1: parse the question.\nReasoning step 2: answer: ${p}`,
  ];
  const generated = prompts.map((p, i) => templates[(p.length + i) % templates.length](p));
  const filtered = generated.filter((t) => t.trim().length >= 8 && !/as an ai language model/i.test(t));
  const seen = new Set();
  const kept = [];
  filtered.forEach((t) => {
    const key = t.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      kept.push(t);
    }
  });
  const records = kept.map((text) => {
    const prompt = prompts[generated.indexOf(text)] || "";
    if (payload.format === "alpaca") return { instruction: prompt, input: "", output: text };
    if (payload.format === "sharegpt")
      return { conversations: [{ from: "human", value: prompt }, { from: "gpt", value: text }] };
    if (payload.format === "text") return { text: `### User\n${prompt}\n\n### Assistant\n${text}` };
    return { messages: [{ role: "user", content: prompt }, { role: "assistant", content: text }] };
  });
  return {
    result: {
      stats: {
        generated: generated.length,
        after_filters: filtered.length,
        after_dedupe: kept.length,
        format: payload.format,
      },
    },
    records,
  };
}

els.run.addEventListener("click", run);
loadCatalogue();
