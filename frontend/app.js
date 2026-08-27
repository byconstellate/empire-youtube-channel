const API_BASE = (document.querySelector("meta[name=\"api-base\"]")?.content || window.EMPIRE_API_BASE || new URLSearchParams(window.location.search).get("api") || "").replace(/\/$/, "");
function apiUrl(path) { return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`; }
function backendUnavailableMessage() { return "Instant preview is ready. Add ?api=https://your-backend-url to this Pages URL for Pexels footage and MP4 export."; }
const sampleScript = {
  project_id: "empire_youtube_channel",
  scenes: [
    { scene_id: "1", text: "Your business doesn't need another strategy.", duration_seconds: 5, scene_type: "video", search_query: "woman working laptop business" },
    { scene_id: "2", text: "It needs you to actually pick one.", duration_seconds: 5, scene_type: "text" }
  ]
};
const input = document.querySelector("#script-input");
const scenes = document.querySelector("#scenes");
const count = document.querySelector("#scene-count");
const error = document.querySelector("#script-error");
const renderButton = document.querySelector("#render-button");
const loadButton = document.querySelector("#load-script");
const renderHint = document.querySelector("#render-status");
renderButton.innerHTML = "Export MP4 <span>→</span>";
if (renderHint) renderHint.textContent = "Instant browser preview is ready; MP4 export runs separately in the background.";
let currentScript = sampleScript;
input.value = JSON.stringify(sampleScript, null, 2);

function renderScenes(script) {
  const total = script.scenes.reduce((sum, scene) => sum + Number(scene.duration_seconds), 0);
  count.textContent = `${script.scenes.length} scenes · ${total} sec`;
  scenes.innerHTML = script.scenes.map((scene, index) => `
    <article class="scene" data-scene="${index}">
      <span class="scene-number">${String(index + 1).padStart(2, "0")} </span>
      <div class="scene-copy"><strong>${escapeHtml(scene.text)}</strong><small>${scene.duration_seconds} sec${scene.search_query ? ` · ${escapeHtml(scene.search_query)}` : " · Full-screen text"}</small>
        ${scene.scene_type === "video" ? '<div class="scene-actions"><button type="button" data-action="approve" aria-pressed="false">Approve footage</button><button type="button" data-action="reject" aria-pressed="false">Reject candidate</button></div>' : ""}
      </div><span class="scene-type">${scene.scene_type.toUpperCase()}</span>
    </article>`).join("");
}
function ensureBrowserPreviewPanel() {
  let preview = document.querySelector("#browser-preview");
  if (preview) return preview;
  const renderBar = document.querySelector(".render-bar");
  if (!renderBar || !renderBar.parentElement) return null;
  const panel = document.createElement("section");
  panel.className = "panel instant-preview-panel";
  panel.innerHTML = `<div class="panel-heading"><div><span class="step">04</span><h2>Instant browser preview</h2></div><span class="muted">No voice or FFmpeg</span></div><div id="browser-preview" class="browser-preview" aria-live="polite"></div>`;
  renderBar.parentElement.insertBefore(panel, renderBar);
  return panel.querySelector("#browser-preview");
}
function renderBrowserPreview(script) {
  const preview = ensureBrowserPreviewPanel();
  if (!preview) return;
  preview.innerHTML = script.scenes.map((scene, index) => {
    const videoUrl = scene.selected_video?.preview_url || "";
    const media = scene.scene_type === "video" && videoUrl
      ? `<video src="${escapeHtml(videoUrl)}" muted playsinline controls preload="metadata"></video>`
      : `<div class="preview-placeholder ${scene.scene_type === "text" ? "preview-text" : "preview-video"}"><span>${scene.scene_type === "text" ? "TEXT SCENE" : "VIDEO SCENE"}</span><strong>${escapeHtml(scene.text)}</strong></div>`;
    return `<article class="browser-preview-card"><div class="browser-preview-media">${media}</div><div class="browser-preview-label"><span>${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(scene.text)}</strong><small>${scene.duration_seconds}s · ${scene.scene_type === "video" ? (videoUrl ? "footage loaded" : "footage pending") : "full-screen text"}</small></div></article>`;
  }).join("");
}
function plainTextToScript(text) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) throw new Error("Add at least one non-empty line to your script.");
  return { project_id: "empire_text_script", scenes: lines.map((line, index) => ({ scene_id: String(index + 1), text: line, duration_seconds: 5, scene_type: "video" })) };
}
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char])); }
async function loadFootagePreviews(script, expand = false) {
  if (!API_BASE && /github\.io$/i.test(window.location.hostname)) throw new Error(backendUnavailableMessage());
  const response = await fetch(apiUrl("/api/preview"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...script, expand }) });
  if (!response.ok) throw new Error(await response.text() || "Could not load Pexels previews.");
  const data = await response.json();
  data.scenes.forEach((preview) => {
    const scene = script.scenes.find((item) => String(item.scene_id) === String(preview.scene_id));
    const article = [...scenes.querySelectorAll(".scene")].find((item) => item.dataset.scene === String(script.scenes.indexOf(scene)));
    if (!scene || !article) return;
    const box = document.createElement("div"); box.className = "footage-previews";
    const label = document.createElement("small"); label.textContent = "Preview footage, then approve one:"; box.appendChild(label);
    preview.candidates.forEach((candidate, index) => {
      const button = document.createElement("button"); button.type = "button"; button.className = "footage-choice";
      const video = document.createElement("video"); video.src = candidate.preview_url; video.controls = true; video.muted = true; video.preload = "metadata"; video.title = `Preview Pexels candidate ${index + 1}`; button.appendChild(video);
      const caption = document.createElement("span"); caption.textContent = `Candidate ${index + 1}`; button.appendChild(caption);
      button.addEventListener("click", () => {
        scene.selected_video = candidate; box.querySelectorAll(".footage-choice").forEach((item) => item.classList.remove("approved")); button.classList.add("approved"); caption.textContent = "Approved ✓"; renderBrowserPreview(script);
      });
      box.appendChild(button);
    });
    article.querySelector(".scene-copy").appendChild(box);
  });
}
async function loadScript() {
  try {
    let script;
    try { script = JSON.parse(input.value); } catch (parseError) { script = plainTextToScript(input.value); }
    if (!script.project_id || !Array.isArray(script.scenes) || !script.scenes.length) throw new Error("Add a project_id and at least one scene.");
    if (script.scenes.some((scene) => !scene || !scene.text || !scene.scene_type || !scene.duration_seconds)) throw new Error("Each scene needs text, scene_type, and duration_seconds.");
    currentScript = script;
    error.textContent = "";
    renderScenes(script);
    renderBrowserPreview(script);
    loadButton.innerHTML = "Script loaded ✓";
    window.setTimeout(() => { loadButton.innerHTML = "Load script + find more <span>→</span>"; }, 1800);
    loadFootagePreviews(script, true).catch((err) => { error.textContent = err instanceof Error ? err.message : backendUnavailableMessage(); });
  } catch (err) {
    error.textContent = err instanceof Error ? err.message : "Could not load that script.";
  }
}
loadButton.addEventListener("click", loadScript);
document.querySelector("#script-file")?.addEventListener("change", async (event) => { const file = event.target.files?.[0]; if (!file) return; input.value = await file.text(); loadScript(); });
scenes.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]"); if (!button) return;
  event.preventDefault();
  const actions = button.parentElement.querySelectorAll("button[data-action]");
  const approved = button.dataset.action === "approve";
  actions.forEach((action) => {
    const selected = action === button;
    action.classList.toggle("approved", selected && approved);
    action.classList.toggle("rejected", selected && !approved);
    action.setAttribute("aria-pressed", String(selected));
    action.textContent = selected ? (approved ? "Approved" : "Rejected") : (action.dataset.action === "approve" ? "Approve footage" : "Reject candidate");
  });
});
renderButton.addEventListener("click", async () => {
  const title = document.querySelector("#render-title");
  const status = document.querySelector("#render-status");
  renderButton.disabled = true; renderButton.textContent = "Rendering…";
  title.textContent = "Creating your video";
  status.textContent = "Generating voice, fetching footage, and encoding a 1280 × 720 MP4…";
  error.textContent = "";
  try {
    if (!API_BASE && /github\.io$/i.test(window.location.hostname)) throw new Error(backendUnavailableMessage());
    const response = await fetch(apiUrl("/api/render"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...currentScript, language: document.querySelector("#language").value }) });
    if (!response.ok) throw new Error(await response.text() || "The renderer could not start.");
    if (!response.ok) { const detail = await response.text(); throw new Error(`Render start failed with HTTP ${response.status}: ${detail.slice(0, 240)}`); }
    const job = await response.json();
    let state = { status: "queued" };
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      const statusResponse = await fetch(apiUrl(job.status_url));
      if (!statusResponse.ok) { const detail = await statusResponse.text(); throw new Error(`Render status failed with HTTP ${statusResponse.status}: ${detail.slice(0, 240)}`); }
      state = await statusResponse.json();
      if (state.status === "failed") throw new Error(state.error || "Render failed.");
      if (state.status === "complete") break;
      status.textContent = `Rendering video… ${Math.round((attempt + 1) / 180 * 100)}%`;
    }
    if (state.status !== "complete") throw new Error("Render is taking longer than expected. Check the service logs.");
    const downloadResponse = await fetch(apiUrl(job.download_url));
    if (!downloadResponse.ok) throw new Error(await downloadResponse.text() || "The video download failed.");
    const blob = await downloadResponse.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = `${currentScript.project_id}-landscape.mp4`; link.click();
    URL.revokeObjectURL(url);
    title.textContent = "Video created"; status.textContent = "Your horizontal 1280 × 720 MP4 has downloaded.";
  } catch (err) {
    title.textContent = "Render failed"; status.textContent = err.message; error.textContent = err.message;
  } finally { renderButton.disabled = false; renderButton.innerHTML = "Export MP4 <span>→</span>"; }
});
renderScenes(currentScript);
renderBrowserPreview(currentScript);