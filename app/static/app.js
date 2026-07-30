const byId = (id) => document.getElementById(id);
const form = byId("scrape-form");
let currentUrl = "";

function setHidden(id, hidden) {
  byId(id).classList.toggle("hidden", hidden);
}

function updateWordCount() {
  const words = byId("content").value.trim().split(/\s+/).filter(Boolean).length;
  byId("word-count").textContent = `${words.toLocaleString()} words`;
}

// --- Safe Markdown -> HTML preview ------------------------------------
// Renders only the Markdown subset the scraper itself produces (headings,
// paragraphs, ordered/nested lists, tables, code, blockquotes, links,
// images). Text is escaped before insertion and link/image URLs are
// scheme-checked, so this is safe to use with innerHTML even though the
// source Markdown originated from an untrusted scraped web page.

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeUrl(rawUrl) {
  const trimmed = (rawUrl || "").trim();
  const schemeMatch = trimmed.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
  if (schemeMatch && !["http", "https", "mailto", "tel"].includes(schemeMatch[1].toLowerCase())) {
    return "#";
  }
  return trimmed;
}

const INLINE_PATTERN = /`([^`]+)`|!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]*)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*/g;

function renderInline(rawText) {
  let out = "";
  let lastIndex = 0;
  let match;
  INLINE_PATTERN.lastIndex = 0;
  while ((match = INLINE_PATTERN.exec(rawText)) !== null) {
    out += escapeHtml(rawText.slice(lastIndex, match.index));
    if (match[1] !== undefined) {
      out += `<code>${escapeHtml(match[1])}</code>`;
    } else if (match[2] !== undefined) {
      out += `<img alt="${escapeHtml(match[2])}" src="${escapeHtml(safeUrl(match[3]))}" loading="lazy">`;
    } else if (match[4] !== undefined) {
      out += `<a href="${escapeHtml(safeUrl(match[5]))}" target="_blank" rel="noopener noreferrer">${escapeHtml(match[4])}</a>`;
    } else if (match[6] !== undefined) {
      out += `<strong>${escapeHtml(match[6])}</strong>`;
    } else if (match[7] !== undefined) {
      out += `<em>${escapeHtml(match[7])}</em>`;
    }
    lastIndex = INLINE_PATTERN.lastIndex;
  }
  out += escapeHtml(rawText.slice(lastIndex));
  return out;
}

function renderMarkdown(markdown) {
  const lines = markdown.split("\n");
  let html = "";
  let listStack = []; // {type, indent, liOpen}

  function closeCurrentLi() {
    const top = listStack[listStack.length - 1];
    if (top && top.liOpen) {
      html += "</li>";
      top.liOpen = false;
    }
  }
  function closeListsDeeperThan(indent) {
    while (listStack.length && listStack[listStack.length - 1].indent > indent) {
      closeCurrentLi();
      html += listStack.pop().type === "ol" ? "</ol>" : "</ul>";
    }
  }
  function closeAllLists() {
    closeListsDeeperThan(-1);
  }

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      closeAllLists();
      i++;
      continue;
    }

    if (/^```/.test(line.trim())) {
      closeAllLists();
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      html += `<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`;
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      closeAllLists();
      const level = headingMatch[1].length;
      html += `<h${level}>${renderInline(headingMatch[2])}</h${level}>`;
      i++;
      continue;
    }

    if (line.trim().startsWith("|") && lines[i + 1] && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      closeAllLists();
      const toCells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const headerCells = toCells(line);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        bodyRows.push(toCells(lines[i]));
        i++;
      }
      html += "<table><thead><tr>" +
        headerCells.map((c) => `<th>${renderInline(c)}</th>`).join("") +
        "</tr></thead><tbody>" +
        bodyRows.map((row) => "<tr>" + row.map((c) => `<td>${renderInline(c)}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>";
      continue;
    }

    if (line.startsWith(">")) {
      closeAllLists();
      const quoteLines = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      html += `<blockquote><p>${quoteLines.map(renderInline).join("<br>")}</p></blockquote>`;
      continue;
    }

    const listMatch = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (listMatch) {
      const indent = listMatch[1].length;
      const type = /\d+\./.test(listMatch[2]) ? "ol" : "ul";
      const content = listMatch[3];
      closeListsDeeperThan(indent);
      let top = listStack[listStack.length - 1];
      if (!top || top.indent < indent) {
        html += type === "ol" ? "<ol>" : "<ul>";
        listStack.push({ type, indent, liOpen: false });
      } else if (top.type !== type) {
        closeCurrentLi();
        html += listStack.pop().type === "ol" ? "</ol>" : "</ul>";
        html += type === "ol" ? "<ol>" : "<ul>";
        listStack.push({ type, indent, liOpen: false });
      } else {
        closeCurrentLi();
      }
      html += `<li>${renderInline(content)}`;
      listStack[listStack.length - 1].liOpen = true;
      i++;
      continue;
    }

    closeAllLists();
    const paraLines = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,6}\s+/.test(lines[i]) &&
      !/^```/.test(lines[i].trim()) &&
      !lines[i].startsWith(">") &&
      !/^(\s*)([-*]|\d+\.)\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("|")
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    html += `<p>${paraLines.map(renderInline).join(" ")}</p>`;
  }
  closeAllLists();
  return html;
}

function refreshPreview() {
  const markdown = byId("content").value.trim();
  byId("preview").innerHTML = markdown
    ? renderMarkdown(markdown)
    : '<p class="empty-hint">Nothing to preview yet.</p>';
}

// --- Staged progress feedback -------------------------------------------
// The scrape is a single request/response with no server-sent progress, so
// these steps advance on a plausible fixed cadence rather than tracking the
// backend in real time. The final step only completes once the response
// actually arrives, so it never claims to be further along than it is.

const PROGRESS_STEPS = ["fetch", "detect", "extract", "clean"];
let progressStepTimer = null;
let progressElapsedTimer = null;

function setStepState(step, state) {
  const el = document.querySelector(`.step[data-step="${step}"]`);
  el.classList.remove("pending", "active", "done");
  el.classList.add(state);
}

function resetProgress() {
  PROGRESS_STEPS.forEach((step) => setStepState(step, "pending"));
  byId("elapsed").textContent = "0.0s";
}

function startProgress() {
  resetProgress();
  let stepIndex = 0;
  setStepState(PROGRESS_STEPS[0], "active");
  progressStepTimer = setInterval(() => {
    if (stepIndex < PROGRESS_STEPS.length - 1) {
      setStepState(PROGRESS_STEPS[stepIndex], "done");
      stepIndex++;
      setStepState(PROGRESS_STEPS[stepIndex], "active");
    }
  }, 1000);

  const start = Date.now();
  progressElapsedTimer = setInterval(() => {
    byId("elapsed").textContent = `${((Date.now() - start) / 1000).toFixed(1)}s`;
  }, 100);
}

function finishProgress(success) {
  clearInterval(progressStepTimer);
  clearInterval(progressElapsedTimer);
  if (success) {
    PROGRESS_STEPS.forEach((step) => setStepState(step, "done"));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("scrape-button");
  button.disabled = true;
  byId("scrape-button-label").textContent = "Scraping…";
  setHidden("progress", false);
  setHidden("error", true);
  setHidden("review", true);
  setHidden("approved", true);
  startProgress();
  try {
    const response = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: byId("url").value,
        instructions: byId("instructions").value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The page could not be processed.");
    finishProgress(true);
    currentUrl = data.url;
    byId("title").value = data.title;
    byId("content").value = data.cleaned_text;
    byId("raw-content").textContent = data.raw_text;
    const byline = [data.author, data.published_date].filter(Boolean).join(" · ");
    byId("byline").textContent = byline;
    setHidden("byline", !byline);
    byId("method-badge").textContent = data.method === "browser" ? "Headless browser" : "Direct HTML";
    byId("llm-badge").textContent = data.llm_used ? "LLM cleaned" : "Extraction only";
    byId("warning").textContent = data.warning || "";
    setHidden("warning", !data.warning);
    setHidden("review", false);
    switchTab("edit");
    updateWordCount();
    byId("review").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    finishProgress(false);
    byId("error").textContent = error.message;
    setHidden("error", false);
  } finally {
    button.disabled = false;
    byId("scrape-button-label").textContent = "Scrape page";
    setHidden("progress", true);
  }
});

byId("content").addEventListener("input", updateWordCount);
byId("raw-toggle").addEventListener("click", () => {
  const panel = byId("raw-panel");
  panel.classList.toggle("hidden");
  byId("raw-toggle").textContent = panel.classList.contains("hidden")
    ? "Show raw extraction" : "Hide raw extraction";
});

function switchTab(tab) {
  document.querySelectorAll(".tab-button").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  setHidden("content", tab !== "edit");
  setHidden("preview", tab !== "preview");
  if (tab === "preview") refreshPreview();
}

document.querySelectorAll(".tab-button").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

byId("approve-button").addEventListener("click", async () => {
  const response = await fetch("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: currentUrl,
      title: byId("title").value,
      content: byId("content").value,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    byId("error").textContent = data.detail || "Approval failed.";
    setHidden("error", false);
    return;
  }
  byId("title").value = data.title;
  byId("content").value = data.content;
  setHidden("approved", false);
  byId("approved").scrollIntoView({ behavior: "smooth", block: "center" });
});

byId("copy-button").addEventListener("click", async () => {
  await navigator.clipboard.writeText(byId("content").value);
  byId("copy-button").textContent = "Copied!";
  setTimeout(() => { byId("copy-button").textContent = "Copy content"; }, 1500);
});
