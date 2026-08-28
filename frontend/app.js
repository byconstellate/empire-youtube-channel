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
const renderPreview = document.querySelector("#render-preview");
const renderVideo = document.querySelector("#render-video");
const downloadButton = document.querySelector("#download-button");
let renderedVideoUrl = "";
renderButton.innerHTML = "Export MP4 <span>→</span>";
if (renderHint) renderHint.textContent = "Review your scenes and footage, then render the finished video.";
document.querySelector("#preview-footage")?.remove();
document.querySelector("#more-footage")?.remove();
loadButton.innerHTML = "Load script + find more <span>→</span>";
let currentScript = sampleScript;
input.value = JSON.stringify(sampleScript, null, 2);

function renderScenes(script) {
  const total = script.scenes.reduce((sum, scene) => sum + Number(scene.duration_seconds), 0);
  count.textContent = `${script.scenes.length} scenes · ${total} sec`;
  script.scenes.forEach((scene) => {
    if (scene.scene_type === "video") {
      scene.pan_region = scene.pan_region === "bottom_50" ? "bottom_50" : "top_50";
      scene.pan_direction = scene.pan_direction === "bottom_to_top" ? "bottom_to_top" : "top_to_bottom";
    }
    scene.text_position = scene.text_position === "middle" ? "middle" : "bottom";
  });
  scenes.innerHTML = script.scenes.map((scene, index) => `
    <article class="scene" data-scene="${index}">
      <span class="scene-number">${String(index + 1).padStart(2, "0")} </span>
      <div class="scene-copy"><strong>${escapeHtml(scene.text)}</strong><small>${scene.duration_seconds} sec${scene.search_query ? ` · ${escapeHtml(scene.search_query)}` : " · Full-screen text"}</small>
        ${scene.scene_type === "video" ? `<label class="scene-control">Pan area <select data-pan-region="${index}" aria-label="Pan area for scene ${index + 1}"><option value="top_50" ${scene.pan_region === "top_50" ? "selected" : ""}>Top half</option><option value="bottom_50" ${scene.pan_region === "bottom_50" ? "selected" : ""}>Bottom half</option></select></label><label class="scene-control">Pan motion <select data-pan-direction="${index}" aria-label="Pan motion for scene ${index + 1}"><option value="top_to_bottom" ${scene.pan_direction === "top_to_bottom" ? "selected" : ""}>Top → bottom</option><option value="bottom_to_top" ${scene.pan_direction === "bottom_to_top" ? "selected" : ""}>Bottom → top</option></select></label>` : ""}
        <label class="scene-control">Text position <select data-text-position="${index}" aria-label="Text position for scene ${index + 1}"><option value="bottom" ${scene.text_position === "bottom" ? "selected" : ""}>Bottom (default)</option><option value="middle" ${scene.text_position === "middle" ? "selected" : ""}>Middle</option></select></label>
        ${scene.scene_type === "video" ? `<div class="scene-actions"><button type="button" data-action="approve" aria-pressed="false">Approve footage</button><button type="button" data-action="reject" aria-pressed="false">Reject candidate</button></div>` : ""}
      </div><span class="scene-type">${scene.scene_type.toUpperCase()}</span>
    </article>`).join("");
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
        scene.selected_video = candidate; box.querySelectorAll(".footage-choice").forEach((item) => item.classList.remove("approved")); button.classList.add("approved"); caption.textContent = "Approved ✓";
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
    loadButton.innerHTML = "Script loaded ✓";
    window.setTimeout(() => { loadButton.innerHTML = "Load script + find more <span>→</span>"; }, 1800);
    loadFootagePreviews(script, true).catch((err) => { error.textContent = err instanceof Error ? err.message : backendUnavailableMessage(); });
  } catch (err) {
    error.textContent = err instanceof Error ? err.message : "Could not load that script.";
  }
}
loadButton.addEventListener("click", loadScript);
document.querySelector("#script-file")?.addEventListener("change", async (event) => { const file = event.target.files?.[0]; if (!file) return; input.value = await file.text(); loadScript(); });
scenes.addEventListener("change", (event) => {
  const panRegion = event.target.closest("select[data-pan-region]");
  if (panRegion) {
    const scene = currentScript.scenes[Number(panRegion.dataset.panRegion)];
    if (scene) scene.pan_region = panRegion.value;
    return;
  }
  const panDirection = event.target.closest("select[data-pan-direction]");
  if (panDirection) {
    const scene = currentScript.scenes[Number(panDirection.dataset.panDirection)];
    if (scene) scene.pan_direction = panDirection.value;
    return;
  }
  const textPosition = event.target.closest("select[data-text-position]");
  if (textPosition) {
    const scene = currentScript.scenes[Number(textPosition.dataset.textPosition)];
    if (scene) scene.text_position = textPosition.value;
  }
});
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
    if (renderedVideoUrl) URL.revokeObjectURL(renderedVideoUrl);
    renderedVideoUrl = URL.createObjectURL(blob);
    if (renderVideo && renderPreview && downloadButton) {
      renderVideo.src = renderedVideoUrl;
      renderVideo.load();
      renderPreview.hidden = false;
      downloadButton.disabled = false;
      downloadButton.onclick = () => {
        const link = document.createElement("a");
        link.href = renderedVideoUrl;
        link.download = currentScript.project_id + "-landscape.mp4";
        link.click();
      };
      title.textContent = "Preview ready";
      status.textContent = "Review the rendered video above, then download it when ready.";
      renderPreview.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      const link = document.createElement("a");
      link.href = renderedVideoUrl;
      link.download = currentScript.project_id + "-landscape.mp4";
      link.click();
      title.textContent = "Video created";
      status.textContent = "Your video has downloaded.";
    }
  } catch (err) {
    title.textContent = "Render failed"; status.textContent = err.message; error.textContent = err.message;
  } finally { renderButton.disabled = false; renderButton.innerHTML = "Export MP4 <span>→</span>"; }
});
renderScenes(currentScript);

const lineBuilderStyle = document.createElement("style");
lineBuilderStyle.textContent = ".line-builder{border:2px solid #ff00ff;background:#fff;padding:18px;margin-bottom:16px}.line-builder-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;color:#ff00ff;text-transform:uppercase;letter-spacing:.08em}.line-builder-text{font-size:clamp(22px,3vw,38px);line-height:1.08;margin:0 0 18px;color:#111}.line-builder-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.line-builder-grid label{display:grid;gap:6px;color:#111;font-size:12px;text-transform:uppercase;letter-spacing:.06em}.line-builder-grid select,.line-builder-grid input{font:inherit;border:1px solid #ff00ff;padding:9px;background:#fff;color:#111}.line-builder-actions{display:flex;justify-content:space-between;gap:10px;margin-top:18px}.line-builder-actions button{border:1px solid #ff00ff;background:#fff;color:#ff00ff;padding:10px 14px;font:inherit;cursor:pointer}.line-builder-actions button.primary{background:#ff00ff;color:#fff}.line-builder-actions button:disabled{opacity:.45;cursor:not-allowed}.line-builder-status{display:block;margin:14px 0;color:#8a4a7c;font-size:13px}.line-builder-status.error{color:#c40000}.line-builder-complete{display:grid;gap:8px;margin-top:14px}.line-builder-complete article{display:flex;align-items:center;gap:12px;border-top:1px solid #ffd1f5;padding:10px 0;color:#111}.line-builder-complete article strong{color:#ff00ff;min-width:48px}.line-builder-type{display:flex;gap:8px;margin-bottom:16px}.line-builder-type button{flex:1;border:1px solid #ff00ff;background:#fff;color:#ff00ff;padding:10px;cursor:pointer;font:inherit}.line-builder-type button.active{background:#ff00ff;color:#fff}@media(max-width:700px){.line-builder-grid{grid-template-columns:1fr}.line-builder-actions{flex-direction:column}.line-builder-actions button{width:100%}}";
document.head.appendChild(lineBuilderStyle);
const lineFileInput = document.querySelector("#script-file");
const lineLoadButton = loadButton.cloneNode(true);
loadButton.replaceWith(lineLoadButton);
if (lineFileInput) {
  const replacementFileInput = lineFileInput.cloneNode(true);
  lineFileInput.replaceWith(replacementFileInput);
  replacementFileInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    input.value = await file.text();
    loadLineByLineScript();
  });
}
const uploadTitle = document.querySelector(".upload strong");
const uploadHint = document.querySelector(".upload small");
if (uploadTitle) uploadTitle.textContent = "Load a script — one line becomes one scene";
if (uploadHint) uploadHint.textContent = "Choose video or text for each line, then move to the next";
input.setAttribute("aria-label", "Script lines");
input.placeholder = "One scene per line…";
input.value = sampleScript.scenes.map((scene) => scene.text).join("\n");
let activeLineIndex = 0;
let lineFetchToken = 0;
function parseLineByLineScript() {
  const raw = input.value.trim();
  if (!raw) throw new Error("Add at least one line to your script.");
  let parsed;
  try { parsed = JSON.parse(raw); } catch (parseError) { parsed = null; }
  if (parsed && !Array.isArray(parsed.scenes)) throw new Error("A JSON script must contain a scenes array, or paste one scene per line.");
  const sourceScenes = parsed ? parsed.scenes : raw.split(/\\r?\\n/).map((line) => line.trim()).filter(Boolean).map((text, index) => ({ scene_id: String(index + 1), text, duration_seconds: 5, scene_type: "video", search_query: text }));
  if (!sourceScenes.length) throw new Error("Add at least one line to your script.");
  const normalizedScenes = sourceScenes.map((scene, index) => {
    const normalized = { ...scene, scene_id: String(scene.scene_id || index + 1), text: String(scene.text || "").trim(), duration_seconds: Number(scene.duration_seconds) || 5 };
    if (!normalized.text) throw new Error("Every line needs text.");
    normalized.scene_type = normalized.scene_type === "text" ? "text" : "video";
    normalized.search_query = normalized.scene_type === "video" ? String(normalized.search_query || normalized.text) : "";
    normalized.pan_region = normalized.pan_region === "bottom_50" ? "bottom_50" : "top_50";
    normalized.pan_direction = normalized.pan_direction === "bottom_to_top" ? "bottom_to_top" : "top_to_bottom";
    normalized.text_position = normalized.text_position === "middle" ? "middle" : "bottom";
    return normalized;
  });
  return { project_id: parsed?.project_id || "empire_youtube_channel", scenes: normalizedScenes };
}
function renderLineBuilder() {
  lineFetchToken += 1;
  const requestToken = lineFetchToken;
  if (activeLineIndex >= currentScript.scenes.length) {
    renderScenes(currentScript);
    const review = document.createElement("div");
    review.className = "line-builder-actions";
    review.innerHTML = '<button type="button" class="primary">Edit lines</button>';
    review.querySelector("button").addEventListener("click", () => { activeLineIndex = 0; renderLineBuilder(); });
    scenes.prepend(review);
    return;
  }
  const scene = currentScript.scenes[activeLineIndex];
  const isVideo = scene.scene_type === "video";
  scenes.innerHTML = "";
  const builder = document.createElement("section");
  builder.className = "line-builder";
  builder.innerHTML = '<div class="line-builder-head"><strong>Scene setup</strong><span></span></div><p class="line-builder-text"></p><div class="line-builder-type"><button type="button" data-line-type="video">Video</button><button type="button" data-line-type="text">Text</button></div><div class="line-builder-grid"></div><span class="line-builder-status">Finding footage for this line automatically…</span><div class="line-builder-actions"><button type="button" data-line-prev>← Previous line</button><button type="button" class="primary" data-line-next>Next line →</button></div>';
  builder.querySelector(".line-builder-head span").textContent = "Line " + (activeLineIndex + 1) + " of " + currentScript.scenes.length;
  builder.querySelector(".line-builder-text").textContent = scene.text;
  builder.querySelector('[data-line-type="' + scene.scene_type + '"]').classList.add("active");
  const grid = builder.querySelector(".line-builder-grid");
  const durationLabel = document.createElement("label");
  durationLabel.textContent = "Duration (seconds)";
  durationLabel.innerHTML += '<input type="number" min="1" max="60" step="1" data-line-duration>'; 
  durationLabel.querySelector("input").value = scene.duration_seconds;
  grid.appendChild(durationLabel);
  if (isVideo) {
    const queryLabel = document.createElement("label");
    queryLabel.textContent = "Footage search";
    queryLabel.innerHTML += '<input type="text" data-line-query>'; 
    queryLabel.querySelector("input").value = scene.search_query || scene.text;
    grid.appendChild(queryLabel);
    const panRegionLabel = document.createElement("label");
    panRegionLabel.textContent = "Pan area";
    panRegionLabel.innerHTML += '<select data-pan-region="' + activeLineIndex + '"><option value="top_50">Top half</option><option value="bottom_50">Bottom half</option></select>';
    panRegionLabel.querySelector("select").value = scene.pan_region;
    grid.appendChild(panRegionLabel);
    const panDirectionLabel = document.createElement("label");
    panDirectionLabel.textContent = "Pan motion";
    panDirectionLabel.innerHTML += '<select data-pan-direction="' + activeLineIndex + '"><option value="top_to_bottom">Top → bottom</option><option value="bottom_to_top">Bottom → top</option></select>';
    panDirectionLabel.querySelector("select").value = scene.pan_direction;
    grid.appendChild(panDirectionLabel);
  }
  const textPositionLabel = document.createElement("label");
  textPositionLabel.textContent = "Text position";
  textPositionLabel.innerHTML += '<select data-text-position="' + activeLineIndex + '"><option value="bottom">Bottom</option><option value="middle">Middle</option></select>';
  textPositionLabel.querySelector("select").value = scene.text_position;
  grid.appendChild(textPositionLabel);
  const status = builder.querySelector(".line-builder-status");
  const nextButton = builder.querySelector("[data-line-next]");
  const previousButton = builder.querySelector("[data-line-prev]");
  const syncNextButton = () => { nextButton.disabled = scene.scene_type === "video" && !(scene.selected_video && scene.selected_video.video_files); };
  builder.querySelectorAll("[data-line-type]").forEach((button) => button.addEventListener("click", () => {
    scene.scene_type = button.dataset.lineType;
    if (scene.scene_type === "video") scene.search_query = scene.search_query || scene.text;
    else { scene.search_query = ""; delete scene.selected_video; }
    renderLineBuilder();
  }));
  builder.querySelector('[data-line-duration]').addEventListener("change", (event) => { scene.duration_seconds = Math.max(1, Math.min(60, Number(event.target.value) || 5)); });
  const queryInput = builder.querySelector("[data-line-query]");
  if (queryInput) queryInput.addEventListener("change", (event) => { scene.search_query = event.target.value.trim() || scene.text; renderLineBuilder(); });
  previousButton.disabled = activeLineIndex === 0;
  previousButton.addEventListener("click", () => { if (activeLineIndex > 0) { activeLineIndex -= 1; renderLineBuilder(); } });
  nextButton.textContent = activeLineIndex === currentScript.scenes.length - 1 ? "Finish scene setup ✓" : "Next line →";
  nextButton.addEventListener("click", () => { activeLineIndex += 1; renderLineBuilder(); });
  scenes.appendChild(builder);
  if (!isVideo) {
    status.textContent = "Text scene ready. Choose its position, then continue.";
    syncNextButton();
    return;
  }
  syncNextButton();
  loadFootagePreviews({ project_id: currentScript.project_id, scenes: [scene] }, true).then(() => {
    if (requestToken !== lineFetchToken) return;
    const footageLabel = builder.querySelector(".footage-previews small");
    if (footageLabel) footageLabel.textContent = "Select a video for this line:";
    status.textContent = "Select a video below, then continue to the next line.";
    syncNextButton();
  }).catch((err) => {
    if (requestToken !== lineFetchToken) return;
    status.classList.add("error");
    status.textContent = err instanceof Error ? err.message : backendUnavailableMessage();
    nextButton.disabled = false;
  });
}
lineLoadButton.innerHTML = "Load script <span>→</span>";
lineLoadButton.addEventListener("click", () => {
  try {
    currentScript = parseLineByLineScript();
    activeLineIndex = 0;
    error.textContent = "";
    renderLineBuilder();
  } catch (err) {
    error.textContent = err instanceof Error ? err.message : "Could not load that script.";
  }
});
scenes.addEventListener("click", (event) => {
  if (!event.target.closest(".footage-choice")) return;
  window.setTimeout(() => {
    const active = currentScript.scenes[activeLineIndex];
    const next = scenes.querySelector("[data-line-next]");
    if (active && next) next.disabled = !(active.selected_video && active.selected_video.video_files);
  }, 0);
});
renderLineBuilder();
