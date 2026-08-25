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
let currentScript = sampleScript;
input.value = JSON.stringify(sampleScript, null, 2);

function renderScenes(script) {
  const total = script.scenes.reduce((sum, scene) => sum + Number(scene.duration_seconds), 0);
  count.textContent = `${script.scenes.length} scenes · ${total} sec`;
  scenes.innerHTML = script.scenes.map((scene, index) => `
    <article class="scene" data-scene="${index}">
      <span class="scene-number">${String(index + 1).padStart(2, "0")}</span>
      <div class="scene-copy"><strong>${escapeHtml(scene.text)}</strong><small>${scene.duration_seconds} sec${scene.search_query ? ` · ${escapeHtml(scene.search_query)}` : " · Full-screen text"}</small>
        ${scene.scene_type === "video" ? '<div class="scene-actions"><button type="button" data-action="approve" aria-pressed="false">Approve footage</button><button type="button" data-action="reject" aria-pressed="false">Reject candidate</button></div>' : ""}
      </div><span class="scene-type">${scene.scene_type.toUpperCase()}</span>
    </article>`).join("");
}
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char])); }
function loadScript() {
  try {
    const script = JSON.parse(input.value);
    if (!script.project_id || !Array.isArray(script.scenes) || !script.scenes.length) throw new Error("Add a project_id and at least one scene.");
    currentScript = script; error.textContent = ""; renderScenes(script);
  } catch (err) { error.textContent = err.message; }
}
document.querySelector("#load-script").addEventListener("click", loadScript);
document.querySelector("#script-file").addEventListener("change", async (event) => {
  const file = event.target.files[0]; if (!file) return;
  input.value = await file.text(); loadScript();
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
renderButton.addEventListener("click", () => {
  const title = document.querySelector("#render-title");
  const status = document.querySelector("#render-status");
  renderButton.disabled = true; renderButton.textContent = "Rendering…";
  title.textContent = "Render queued"; status.textContent = "The browser prototype is ready for the Python renderer.";
  setTimeout(() => { title.textContent = "Ready for the renderer"; status.textContent = `Your ${currentScript.scenes.length}-scene landscape video will export to MP4 at 1920 × 1080.`; renderButton.disabled = false; renderButton.innerHTML = "Start render <span>→</span>"; }, 1100);
});
renderScenes(currentScript);