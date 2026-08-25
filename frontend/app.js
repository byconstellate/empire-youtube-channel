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
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char])); }
async function loadFootagePreviews(script) {
  const response = await fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(script) });
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
function loadScript() {
  try {
    const script = JSON.parse(input.value);
    if (!script.project_id || !Array.isArray(script.scenes) || !script.scenes.length) throw new Error("Add a project_id and at least one scene.");
    if (script.scenes.some((scene) => !scene || !scene.text || !scene.scene_type || !scene.duration_seconds)) throw new Error("Each scene needs text, scene_type, and duration_seconds.");
    currentScript = script;
    error.textContent = "";
    renderScenes(script);
    loadButton.innerHTML = "Finding footage…";
    await loadFootagePreviews(script);
    loadButton.innerHTML = "Script loaded ✓";
    window.setTimeout(() => { loadButton.innerHTML = "Load script <span>→</span>"; }, 1800);
  } catch (err) {
    error.textContent = err instanceof Error ? err.message : "Could not load that script.";
  }
}
loadButton.addEventListener("click", loadScript);
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
  status.textContent = "Generating voice, fetching footage, and encoding a 1920 × 1080 MP4…";
  error.textContent = "";
  try {
    const response = await fetch("/api/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...currentScript, language: document.querySelector("#language").value }) });
    if (!response.ok) throw new Error(await response.text() || "The renderer could not start.");
    const job = await response.json();
    let state = { status: "queued" };
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      const statusResponse = await fetch(job.status_url);
      state = await statusResponse.json();
      if (state.status === "failed") throw new Error(state.error || "Render failed.");
      if (state.status === "complete") break;
      status.textContent = `Rendering video… ${Math.round((attempt + 1) / 180 * 100)}%`;
    }
    if (state.status !== "complete") throw new Error("Render is taking longer than expected. Check the service logs.");
    const downloadResponse = await fetch(job.download_url);
    if (!downloadResponse.ok) throw new Error(await downloadResponse.text() || "The video download failed.");
    const blob = await downloadResponse.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = `${currentScript.project_id}-landscape.mp4`; link.click();
    URL.revokeObjectURL(url);
    title.textContent = "Video created"; status.textContent = "Your horizontal 1920 × 1080 MP4 has downloaded.";
  } catch (err) {
    title.textContent = "Render failed"; status.textContent = ""; error.textContent = err.message;
  } finally { renderButton.disabled = false; renderButton.innerHTML = "Start render <span>→</span>"; }
});
renderScenes(currentScript);