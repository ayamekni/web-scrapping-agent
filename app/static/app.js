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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("scrape-button");
  button.disabled = true;
  setHidden("progress", false);
  setHidden("error", true);
  setHidden("review", true);
  setHidden("approved", true);
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
    updateWordCount();
    byId("review").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    byId("error").textContent = error.message;
    setHidden("error", false);
  } finally {
    button.disabled = false;
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

