const API_BASE = (document.querySelector('meta[name="api-base"]')?.content || window.EMPIRE_API_BASE || new URLSearchParams(window.location.search).get("api") || "").replace(/\/$/, "");
function apiUrl(path) { return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`; }
function backendUnavailableMessage() { return "Media search needs the backend. GIFs use GIPHY and videos use Pexels."; }

const TEXT_COLOR_OPTIONS = [
  { value: "#000000", label: "Black" },
  { value: "#ffffff", label: "White" },
  { value: "#00ff00", label: "Green" },
  { value: "#ff00ff", label: "Pink" },
];

function colorSelectHtml(dataAttr, index, selected) {
  return `<select data-${dataAttr}="${index}">` + TEXT_COLOR_OPTIONS.map((o) =>
    `<option value="${o.value}" ${o.value === selected ? "selected" : ""}>${o.label}</option>`
  ).join("") + `</select>`;
}

function normalizeColors(scene) {
  const valid = (v, fallback) => (TEXT_COLOR_OPTIONS.some((o) => o.value === v) ? v : fallback);
  scene.text_color = valid(scene.text_color, "#ff00ff");
  scene.outline_color = valid(scene.outline_color, "#ffffff");
  scene.bg_color = valid(scene.bg_color, "#000000");
}

// These mirror the server's ffmpeg drawtext math (video.py caption_filter) so the
// instant HTML/CSS preview lines up with the real render: fontsize=52 and
// borderw=4 on a 1280-wide canvas become proportional cqw units here, and the
// "bottom" position centers the text block at 72% of the frame height exactly
// like the server's `top = h*0.72-(total_height/2)` formula does.
function scenePreviewBackgroundStyle(scene) {
  if (scene.scene_type === "text") {
    return `background-color:${scene.bg_color || "#000000"};`;
  }
  const image = scene.selected_video && scene.selected_video.image;
  if (image) {
    return `background-image:url('${String(image).replace(/'/g, "%27")}');background-size:cover;background-position:center;`;
  }
  return "background:repeating-linear-gradient(45deg,#1a1a1a,#1a1a1a 10px,#262626 10px,#262626 20px);";
}

function scenePreviewTextStyle(scene) {
  const show = scene.scene_type === "text" ? true : scene.show_text !== false;
  if (!show) return "display:none;";
  const top = scene.text_position === "middle" ? "50%" : "72%";
  const outline = scene.outline_color || "#ffffff";
  return (
    `top:${top};transform:translateY(-50%);` +
    `color:${scene.text_color || "#ff00ff"};` +
    `-webkit-text-stroke:0.31cqw ${outline};paint-order:stroke fill;`
  );
}

function updateScenePreview(index) {
  const scene = currentScript.scenes[index];
  if (!scene) return;
  const box = scenes.querySelector(`.scene-live-preview[data-preview="${index}"]`);
  if (!box) return;
  box.setAttribute("style", scenePreviewBackgroundStyle(scene));
  const text = box.querySelector(`[data-preview-text="${index}"]`);
  if (text) {
    text.setAttribute("style", scenePreviewTextStyle(scene));
    text.textContent = scene.text;
  }
}

function scenePreviewHtml(scene, index) {
  return `
    <div class="scene-live-preview" data-preview="${index}" style="${scenePreviewBackgroundStyle(scene)}">
      <span class="scene-live-preview-text" data-preview-text="${index}" style="${scenePreviewTextStyle(scene)}">${escapeHtml(scene.text)}</span>
    </div>
  `;
}

function parseDurationInput(value, fallback) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return fallback;

  const parts = trimmed.split(":").map((part) => part.trim());

  if (parts.some((part) => part === "" || Number.isNaN(Number(part)))) {
    return fallback;
  }

  let seconds = 0;
  for (const part of parts) seconds = seconds * 60 + Number(part);

  return seconds > 0 ? seconds : fallback;
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

const RECENT_PROJECTS_KEY = "empire_recent_projects";
const MAX_RECENT_PROJECTS = 3;
let autosaveTimer = null;

function loadRecentProjects() {
  try {
    const raw = localStorage.getItem(RECENT_PROJECTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveRecentProjects(list) {
  try {
    localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(list));
  } catch {
    // Storage full or unavailable (e.g. private browsing); autosave just
    // silently stops working rather than breaking the rest of the app.
  }
}

function deriveProjectLabel(script) {
  const firstScene = script.scenes && script.scenes[0];
  const text = firstScene && String(firstScene.text || "").trim();
  if (text) return text.length > 60 ? `${text.slice(0, 57)}…` : text;
  return script.project_id || "Untitled project";
}

function formatRelativeTime(timestamp) {
  const minutes = Math.round((Date.now() - timestamp) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

function formatElapsedTime(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

// A few different code paths fall back to one of a couple of generic
// project_ids ("empire_youtube_channel", "empire_text_script") when the user
// hasn't set their own. Since the recent-projects history is keyed by
// project_id, two genuinely different pieces of work sharing a generic
// default would silently overwrite each other -- which is exactly what
// happened to a real 559-scene project. Give any script still carrying one
// of these defaults (or none at all) a real unique id instead.
const DEFAULT_PROJECT_IDS = new Set(["empire_youtube_channel", "empire_text_script"]);

function ensureUniqueProjectId(script) {
  if (!script.project_id || DEFAULT_PROJECT_IDS.has(script.project_id)) {
    script.project_id = `project_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }
  return script;
}

// Upserts by project_id (editing the same project just refreshes its
// timestamp) and only evicts the oldest *other* entry once a genuinely new
// project pushes the list past MAX_RECENT_PROJECTS.
function upsertRecentProject(script) {
  if (!script || !script.project_id || !Array.isArray(script.scenes) || !script.scenes.length) return;
  const list = loadRecentProjects();
  const existingIndex = list.findIndex((item) => item.project_id === script.project_id);
  const entry = {
    project_id: script.project_id,
    label: deriveProjectLabel(script),
    saved_at: Date.now(),
    script
  };
  if (existingIndex !== -1) {
    list[existingIndex] = entry;
  } else {
    list.push(entry);
    if (list.length > MAX_RECENT_PROJECTS) {
      list.sort((a, b) => a.saved_at - b.saved_at);
      list.shift();
    }
  }
  saveRecentProjects(list);
  renderRecentProjectsStrip();
}

function removeRecentProject(projectId) {
  saveRecentProjects(loadRecentProjects().filter((item) => item.project_id !== projectId));
  renderRecentProjectsStrip();
}

function scheduleAutosave() {
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(() => upsertRecentProject(currentScript), 400);
}

function renderRecentProjectsStrip() {
  let strip = document.querySelector("#recent-projects-strip");
  const list = loadRecentProjects().sort((a, b) => b.saved_at - a.saved_at);

  if (!list.length) {
    if (strip) strip.remove();
    return;
  }

  if (!strip) {
    strip = document.createElement("div");
    strip.id = "recent-projects-strip";
    strip.className = "recent-projects";
    document.querySelector(".script-panel .panel-heading")?.after(strip);
  }

  strip.innerHTML =
    `<small class="recent-projects-label">Resume a recent project</small>` +
    `<div class="recent-projects-list">${list.map((item) => `
      <div class="recent-project-card">
        <button type="button" class="recent-project-resume" data-resume="${escapeHtml(item.project_id)}">
          <strong>${escapeHtml(item.label)}</strong>
          <small>${formatRelativeTime(item.saved_at)}</small>
        </button>
        <button type="button" class="recent-project-dismiss" data-dismiss="${escapeHtml(item.project_id)}" aria-label="Remove ${escapeHtml(item.label)} from recent projects">✕</button>
      </div>
    `).join("")}</div>`;
}

document.addEventListener("click", (event) => {
  const resumeButton = event.target.closest("[data-resume]");
  if (resumeButton) {
    const entry = loadRecentProjects().find((item) => item.project_id === resumeButton.dataset.resume);
    if (entry) {
      currentScript = normalizeScript(entry.script);
      input.value = JSON.stringify(currentScript, null, 2);
      error.textContent = "";
      renderScenes(currentScript);
    }
    return;
  }
  const dismissButton = event.target.closest("[data-dismiss]");
  if (dismissButton) {
    removeRecentProject(dismissButton.dataset.dismiss);
  }
});

renderRecentProjectsStrip();

const sampleScript = {
  project_id: "empire_youtube_channel",
  scenes: [
    {
      scene_id: "1",
      text: "Your business doesn't need another strategy.",
      duration_seconds: 5,
      scene_type: "video",
      search_query: "woman working laptop business"
    },
    {
      scene_id: "2",
      text: "It needs you to actually pick one.",
      duration_seconds: 5,
      scene_type: "text"
    }
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

let audioToggle = document.querySelector("#audio-enabled");

if (!audioToggle) {
  const audioControl = document.createElement("label");
  audioControl.className = "audio-toggle";
  audioControl.htmlFor = "audio-enabled";
  audioControl.innerHTML = `<input id="audio-enabled" type="checkbox" /><span class="audio-toggle-copy"><strong>Include audio narration</strong><small>Turn off to skip TTS and render a silent MP4.</small></span><span class="audio-toggle-switch" aria-hidden="true"></span>`;
  document.querySelector(".voice-panel .voice-note")?.before(audioControl);
  audioToggle = audioControl.querySelector("#audio-enabled");
}

let renderedVideoUrl = "";

renderButton.innerHTML = "Export MP4 <span>→</span>";

if (renderHint) {
  renderHint.textContent = "Review your scenes and footage, then render the finished video.";
}

document.querySelector("#preview-footage")?.remove();
document.querySelector("#more-footage")?.remove();

loadButton.innerHTML = "Load script + find more <span>→</span>";

let currentScript = ensureUniqueProjectId({ ...sampleScript });

input.value = JSON.stringify(currentScript, null, 2);

if (audioToggle) {
  audioToggle.checked = currentScript.audio_enabled !== false;
}

function syncAudioToggle() {
  if (audioToggle) {
    audioToggle.checked = currentScript.audio_enabled !== false;
  }
}

audioToggle?.addEventListener("change", () => {
  currentScript.audio_enabled = audioToggle.checked;
});

function renderScenes(script) {
  count.textContent = `${script.scenes.length} scenes`;

  script.scenes.forEach((scene) => {
    if (scene.scene_type !== "text") {
      scene.pan_region = scene.pan_region === "bottom_50" ? "bottom_50" : "top_50";
      scene.pan_direction = scene.pan_direction === "bottom_to_top" ? "bottom_to_top" : "top_to_bottom";
      scene.show_text = scene.show_text !== false;
    }

    scene.text_position = scene.text_position === "middle" ? "middle" : "bottom";
    scene.duration_seconds = Number(scene.duration_seconds) > 0 ? Number(scene.duration_seconds) : 0;

    normalizeColors(scene);
  });

  scenes.innerHTML = script.scenes.map((scene, index) => `
    <article class="scene" data-scene="${index}">
      <span class="scene-number">${String(index + 1).padStart(2, "0")} </span>

      <div class="scene-copy">
        <div class="scene-copy-header">
          <textarea
            class="scene-text-input"
            data-scene-text="${index}"
            rows="2"
            aria-label="Text for scene ${index + 1}"
          >${escapeHtml(scene.text)}</textarea>
          <button
            type="button"
            class="scene-delete"
            data-delete-scene="${index}"
            aria-label="Delete scene ${index + 1}"
            title="Delete this scene"
          >✕</button>
        </div>

        <small>
          ${scene.scene_type === "text"
            ? "Full-screen text"
            : (scene.scene_type === "gif" ? "GIPHY GIF" : "Pexels video")}
        </small>

        ${scenePreviewHtml(scene, index)}

        ${scene.scene_type !== "text" ? `
          <label class="scene-control">
            Framing
            <select data-pan-mode="${index}" aria-label="Framing for scene ${index + 1}">
              <option value="pan" ${(!scene.pan_mode || scene.pan_mode === "pan") ? "selected" : ""}>Pan (animated)</option>
              <option value="static_top" ${scene.pan_mode === "static_top" ? "selected" : ""}>Static — top</option>
              <option value="static_middle" ${scene.pan_mode === "static_middle" ? "selected" : ""}>Static — middle</option>
              <option value="static_bottom" ${scene.pan_mode === "static_bottom" ? "selected" : ""}>Static — bottom</option>
            </select>
          </label>

          ${(!scene.pan_mode || scene.pan_mode === "pan") ? `
            <label class="scene-control">
              Pan area
              <select data-pan-region="${index}" aria-label="Pan area for scene ${index + 1}">
                <option value="top_50" ${scene.pan_region === "top_50" ? "selected" : ""}>Top half</option>
                <option value="bottom_50" ${scene.pan_region === "bottom_50" ? "selected" : ""}>Bottom half</option>
              </select>
            </label>

            <label class="scene-control">
              Pan motion
              <select data-pan-direction="${index}" aria-label="Pan motion for scene ${index + 1}">
                <option value="top_to_bottom" ${scene.pan_direction === "top_to_bottom" ? "selected" : ""}>Top → bottom</option>
                <option value="bottom_to_top" ${scene.pan_direction === "bottom_to_top" ? "selected" : ""}>Bottom → top</option>
              </select>
            </label>
          ` : ""}
        ` : ""}

        <label class="scene-control">
          Text position
          <select data-text-position="${index}" aria-label="Text position for scene ${index + 1}">
            <option value="bottom" ${scene.text_position === "bottom" ? "selected" : ""}>Bottom (default)</option>
            <option value="middle" ${scene.text_position === "middle" ? "selected" : ""}>Middle</option>
          </select>
        </label>

        <label class="scene-control">
          Duration (mm:ss)${scene.duration_seconds === 0 ? " — auto (matches voice)" : ""}
          <input
            type="text"
            data-duration="${index}"
            value="${formatDuration(scene.duration_seconds)}"
            placeholder="0:00 = auto"
            aria-label="Duration for scene ${index + 1}${scene.duration_seconds === 0 ? ", currently automatic, matching the voice length" : ""}"
          />
        </label>

        <label class="scene-control">
          Text color
          ${colorSelectHtml("text-color", index, scene.text_color)}
        </label>

        <label class="scene-control">
          Outline color
          ${colorSelectHtml("outline-color", index, scene.outline_color)}
        </label>

        ${scene.scene_type === "text" ? `
          <label class="scene-control">
            Background color
            ${colorSelectHtml("bg-color", index, scene.bg_color)}
          </label>
        ` : ""}

        ${scene.scene_type !== "text" ? `
          <label class="scene-control scene-control-checkbox">
            <input
              type="checkbox"
              data-show-text="${index}"
              aria-label="Show text overlay for scene ${index + 1}"
              ${scene.show_text !== false ? "checked" : ""}
            >
            Show text overlay
          </label>
        ` : ""}

        ${scene.scene_type !== "text" ? `
          <div class="scene-actions">
            <button type="button" data-action="approve" aria-pressed="false">
              Approve footage
            </button>
            <button type="button" data-action="reject" aria-pressed="false">
              Reject candidate
            </button>
          </div>
        ` : ""}
      </div>

      <span class="scene-type">${scene.scene_type.toUpperCase()}</span>
    </article>
  `).join("");
}

function plainTextToScript(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) {
    throw new Error("Add at least one non-empty line to your script.");
  }

  return {
    project_id: "empire_text_script",
    scenes: lines.map((line, index) => ({
      scene_id: String(index + 1),
      text: line,
      duration_seconds: 5,
      scene_type: "text"
    }))
  };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

async function readApiError(response, fallback) {
  try {
    const data = await response.json();
    return data?.error || fallback;
  } catch {
    return fallback;
  }
}

function normalizeScript(script) {
  const withUniqueId = ensureUniqueProjectId({ ...script });
  return {
    ...withUniqueId,
    audio_enabled: withUniqueId.audio_enabled !== false,
    scenes: withUniqueId.scenes.map((scene, index) => {
      const normalized = {
        ...scene,
        scene_id: String(scene.scene_id || index + 1),
        text: String(scene.text || "").trim(),
        duration_seconds: Number(scene.duration_seconds) || 0
      };

      if (!normalized.text) {
        throw new Error("Every line needs text.");
      }

      normalized.scene_type = ["text", "gif", "video"].includes(scene.scene_type)
        ? scene.scene_type
        : "text";

      normalized.search_query =
        normalized.scene_type === "text"
          ? ""
          : String(normalized.search_query || normalized.text);

      normalized.pan_region =
        normalized.pan_region === "bottom_50"
          ? "bottom_50"
          : "top_50";

      normalized.pan_direction =
        normalized.pan_direction === "bottom_to_top"
          ? "bottom_to_top"
          : "top_to_bottom";

      normalized.text_position =
        normalized.text_position === "middle"
          ? "middle"
          : "bottom";

      normalized.show_text =
        normalized.scene_type === "text"
          ? true
          : normalized.show_text !== false;

      normalizeColors(normalized);

      return normalized;
    })
  };
}

async function loadFootagePreviews(script, expand = false) {
  if (!API_BASE && /github\.io$/i.test(window.location.hostname)) {
    throw new Error(backendUnavailableMessage());
  }

  const response = await fetch(apiUrl("/api/preview"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      ...script,
      expand
    })
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Could not load media previews."));
  }

  const data = await response.json();

  data.scenes.forEach((preview) => {
    const scene = script.scenes.find(
      (item) => String(item.scene_id) === String(preview.scene_id)
    );

    const article = [...scenes.querySelectorAll(".scene")].find(
      (item) => item.dataset.scene === String(script.scenes.indexOf(scene))
    );

    const target =
      article?.querySelector(".scene-copy") ||
      scenes.querySelector(".line-builder");

    if (!scene || !target) return;

    const existing = target.querySelector(".footage-previews");

    if (existing) existing.remove();

    const box = document.createElement("div");
    box.className = "footage-previews";

    const providerName =
      scene.scene_type === "gif"
        ? "GIPHY GIF"
        : "Pexels video";

    const label = document.createElement("small");
    label.textContent = `Select a ${providerName} for this line:`;
    box.appendChild(label);

    if (!preview.candidates.length) {
      const empty = document.createElement("span");
      empty.className = "footage-empty";
      empty.textContent = "No results for this search.";
      box.appendChild(empty);
    }

    preview.candidates.forEach((candidate, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "footage-choice";

      const video = document.createElement("video");
      video.src = candidate.preview_url;
      video.controls = true;
      video.muted = true;
      video.preload = "metadata";
      video.title = `Preview ${providerName} candidate ${index + 1}`;

      button.appendChild(video);

      const caption = document.createElement("span");
      caption.textContent = `Candidate ${index + 1}`;
      button.appendChild(caption);

      button.addEventListener("click", () => {
        scene.selected_video = candidate;
        updateScenePreview(currentScript.scenes.indexOf(scene));
        scheduleAutosave();

        box.querySelectorAll(".footage-choice").forEach((item) => {
          item.classList.remove("approved");
        });

        button.classList.add("approved");
        caption.textContent = "Approved ✓";
      });

      box.appendChild(button);
    });

    target.appendChild(box);
  });

  return data;
}

async function loadScript() {
  try {
    let script;

    try {
      script = JSON.parse(input.value);
    } catch (parseError) {
      script = plainTextToScript(input.value);
    }

    if (!script.project_id || !Array.isArray(script.scenes) || !script.scenes.length) {
      throw new Error("Add a project_id and at least one scene.");
    }

    if (script.scenes.some((scene) => !scene || !scene.text)) {
      throw new Error("Each scene needs text.");
    }

    currentScript = normalizeScript(script);
    syncAudioToggle();
    error.textContent = "";

    renderScenes(currentScript);
    scheduleAutosave();

    loadButton.innerHTML = "Script loaded ✓";

    window.setTimeout(() => {
      loadButton.innerHTML = "Load script + find more <span>→</span>";
    }, 1800);

    loadFootagePreviews(currentScript, true).catch((err) => {
      error.textContent =
        err instanceof Error
          ? err.message
          : backendUnavailableMessage();
    });
  } catch (err) {
    error.textContent =
      err instanceof Error
        ? err.message
        : "Could not load that script.";
  }
}

loadButton.addEventListener("click", loadScript);

document.querySelector("#script-file")?.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];

  if (!file) return;

  input.value = await file.text();
  loadScript();
});

scenes.addEventListener("change", (event) => {
  const textInput = event.target.closest("textarea[data-scene-text]");

  if (textInput) {
    const index = Number(textInput.dataset.sceneText);
    const scene = currentScript.scenes[index];

    if (scene) {
      const trimmed = textInput.value.trim();

      if (!trimmed) {
        error.textContent = "A scene's text can't be empty.";
        textInput.value = scene.text;
        return;
      }

      error.textContent = "";
      scene.text = trimmed;
      textInput.value = trimmed;
      updateScenePreview(index);
    }

    return;
  }

  const durationInput = event.target.closest("input[data-duration]");

  if (durationInput) {
    const index = Number(durationInput.dataset.duration);
    const scene = currentScript.scenes[index];

    if (scene) {
      const parsed = parseDurationInput(
        durationInput.value,
        scene.duration_seconds
      );

      scene.duration_seconds = parsed;
      durationInput.value = formatDuration(parsed);
    }

    return;
  }

  const panMode = event.target.closest("select[data-pan-mode]");

  if (panMode) {
    const scene =
      currentScript.scenes[Number(panMode.dataset.panMode)];

    if (scene) {
      scene.pan_mode = panMode.value;
      if (scenes.querySelector(".line-builder")) {
        renderLineBuilder();
      } else {
        renderScenes(currentScript);
      }
      scheduleAutosave();
    }

    return;
  }

  const panRegion = event.target.closest("select[data-pan-region]");

  if (panRegion) {
    const scene =
      currentScript.scenes[Number(panRegion.dataset.panRegion)];

    if (scene) {
      scene.pan_region = panRegion.value;
    }

    return;
  }

  const panDirection = event.target.closest("select[data-pan-direction]");

  if (panDirection) {
    const scene =
      currentScript.scenes[Number(panDirection.dataset.panDirection)];

    if (scene) {
      scene.pan_direction = panDirection.value;
    }

    return;
  }

  const textPosition = event.target.closest("select[data-text-position]");

  if (textPosition) {
    const scene =
      currentScript.scenes[Number(textPosition.dataset.textPosition)];

    if (scene) {
      scene.text_position = textPosition.value;
      updateScenePreview(Number(textPosition.dataset.textPosition));
    }

    return;
  }

  const textColor = event.target.closest("select[data-text-color]");

  if (textColor) {
    const scene =
      currentScript.scenes[Number(textColor.dataset.textColor)];

    if (scene) {
      scene.text_color = textColor.value;
      updateScenePreview(Number(textColor.dataset.textColor));
    }

    return;
  }

  const outlineColor =
    event.target.closest("select[data-outline-color]");

  if (outlineColor) {
    const scene =
      currentScript.scenes[Number(outlineColor.dataset.outlineColor)];

    if (scene) {
      scene.outline_color = outlineColor.value;
      updateScenePreview(Number(outlineColor.dataset.outlineColor));
    }

    return;
  }

  const bgColor = event.target.closest("select[data-bg-color]");

  if (bgColor) {
    const scene =
      currentScript.scenes[Number(bgColor.dataset.bgColor)];

    if (scene) {
      scene.bg_color = bgColor.value;
      updateScenePreview(Number(bgColor.dataset.bgColor));
    }

    return;
  }

  const showText = event.target.closest("input[data-show-text]");

  if (showText) {
    const scene =
      currentScript.scenes[Number(showText.dataset.showText)];

    if (scene) {
      scene.show_text = showText.checked;
      updateScenePreview(Number(showText.dataset.showText));
    }
  }
});

scenes.addEventListener("change", () => scheduleAutosave());

scenes.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("button[data-delete-scene]");

  if (deleteButton) {
    event.preventDefault();

    if (currentScript.scenes.length <= 1) {
      error.textContent = "A script needs at least one scene.";
      return;
    }

    const index = Number(deleteButton.dataset.deleteScene);
    const scene = currentScript.scenes[index];
    const label = scene ? scene.text.slice(0, 60) : "this scene";

    if (!window.confirm(`Delete scene ${index + 1} ("${label}")? This can't be undone.`)) {
      return;
    }

    currentScript.scenes.splice(index, 1);
    error.textContent = "";
    renderScenes(currentScript);
    scheduleAutosave();
    return;
  }

  const button = event.target.closest("button[data-action]");

  if (!button) return;

  event.preventDefault();

  const actions =
    button.parentElement.querySelectorAll("button[data-action]");

  const approved = button.dataset.action === "approve";

  actions.forEach((action) => {
    const selected = action === button;

    action.classList.toggle(
      "approved",
      selected && approved
    );

    action.classList.toggle(
      "rejected",
      selected && !approved
    );

    action.setAttribute(
      "aria-pressed",
      String(selected)
    );

    action.textContent = selected
      ? (approved ? "Approved" : "Rejected")
      : (action.dataset.action === "approve"
          ? "Approve footage"
          : "Reject candidate");
  });
});

renderButton.addEventListener("click", async () => {
  const title = document.querySelector("#render-title");
  const status = document.querySelector("#render-status");

  renderButton.disabled = true;
  renderButton.textContent = "Rendering…";

  title.textContent = "Creating your video";

  const includeAudio = currentScript.audio_enabled !== false;

  status.textContent = includeAudio
    ? "Generating voice, fetching footage, and encoding a 1280 × 720 MP4…"
    : "Skipping audio and encoding a silent 1280 × 720 MP4…";

  error.textContent = "";

  try {
    if (!API_BASE && /github\.io$/i.test(window.location.hostname)) {
      throw new Error(backendUnavailableMessage());
    }

    const response = await fetch(apiUrl("/api/render"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        ...currentScript,
        audio_enabled: includeAudio,
        language: document.querySelector("#language").value
      })
    });

    if (!response.ok) {
      throw new Error(
        await readApiError(
          response,
          "The renderer could not start."
        )
      );
    }

    const job = await response.json();

    let state = {
      status: "queued"
    };

    // The backend has no real progress reporting (no per-scene status gets
    // written anywhere), so a fabricated percentage would just be a guess
    // dressed up as data. Elapsed time is the honest thing to show instead.
    // Poll fast at first for quick renders, then back off so a long render
    // (now allowed up to 5 days server-side) doesn't hammer the server with
    // requests every 2 seconds for hours on end.
    const pollStartedAt = Date.now();
    const maxPollMs = 6 * 60 * 60 * 1000; // give up checking from this page after 6 hours
    let pollDelayMs = 2000;

    while (Date.now() - pollStartedAt < maxPollMs) {
      await new Promise((resolve) =>
        window.setTimeout(resolve, pollDelayMs)
      );

      const statusResponse =
        await fetch(apiUrl(job.status_url));

      if (!statusResponse.ok) {
        const detail = await statusResponse.text();

        if (statusResponse.status === 404) {
          throw new Error(
            "The Render worker restarted before this job could be tracked. Start the render again."
          );
        }

        throw new Error(
          `Render status failed with HTTP ${statusResponse.status}: ${detail.slice(0, 240)}`
        );
      }

      state = await statusResponse.json();

      if (state.status === "failed") {
        throw new Error(state.error || "Render failed.");
      }

      if (state.status === "complete") {
        break;
      }

      const elapsedSeconds = Math.round((Date.now() - pollStartedAt) / 1000);

      status.textContent = `Rendering video… ${formatElapsedTime(elapsedSeconds)} elapsed`;

      if (elapsedSeconds > 60 && pollDelayMs < 15000) {
        pollDelayMs = 15000;
      }
    }

    if (state.status !== "complete") {
      throw new Error(
        "Still rendering after 6 hours of checking from this page. Long projects can keep going on the server past that -- refresh and check back, or check the service logs."
      );
    }

    const downloadResponse =
      await fetch(apiUrl(job.download_url));

    if (!downloadResponse.ok) {
      throw new Error(
        await downloadResponse.text() ||
        "The video download failed."
      );
    }

    const blob = await downloadResponse.blob();
    removeRecentProject(currentScript.project_id);

    if (renderedVideoUrl) {
      URL.revokeObjectURL(renderedVideoUrl);
    }

    renderedVideoUrl = URL.createObjectURL(blob);

    if (renderVideo && renderPreview && downloadButton) {
      renderVideo.src = renderedVideoUrl;
      renderVideo.load();

      renderPreview.hidden = false;
      downloadButton.disabled = false;

      downloadButton.onclick = () => {
        const link = document.createElement("a");
        link.href = renderedVideoUrl;
        link.download =
          currentScript.project_id + "-landscape.mp4";
        link.click();
      };

      title.textContent = "Preview ready";
      status.textContent =
        "Review the rendered video above, then download it when ready.";

      renderPreview.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    } else {
      const link = document.createElement("a");
      link.href = renderedVideoUrl;
      link.download =
        currentScript.project_id + "-landscape.mp4";
      link.click();

      title.textContent = "Video created";
      status.textContent =
        "Your video has downloaded.";
    }
  } catch (err) {
    title.textContent = "Render failed";
    status.textContent = err.message;
    error.textContent = err.message;
  } finally {
    renderButton.disabled = false;
    renderButton.innerHTML =
      "Export MP4 <span>→</span>";
  }
});

renderScenes(currentScript);

const lineBuilderStyle = document.createElement("style");

lineBuilderStyle.textContent = ".line-builder{border:2px solid #ff00ff;background:#fff;padding:18px;margin-bottom:16px}.line-builder-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;color:#ff00ff;text-transform:uppercase;letter-spacing:.08em}.line-builder-text{font-size:clamp(22px,3vw,38px);line-height:1.08;margin:0 0 18px;color:#111}.line-builder-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.line-builder-grid label{display:grid;gap:6px;color:#111;font-size:12px;text-transform:uppercase;letter-spacing:.06em}.line-builder-grid select,.line-builder-grid input{font:inherit;border:1px solid #ff00ff;padding:9px;background:#fff;color:#111}.line-builder-actions{display:flex;justify-content:space-between;gap:10px;margin-top:18px}.line-builder-actions button{border:1px solid #ff00ff;background:#fff;color:#ff00ff;padding:10px 14px;font:inherit;cursor:pointer}.line-builder-actions button.primary{background:#ff00ff;color:#fff}.line-builder-actions button:disabled{opacity:.45;cursor:not-allowed}.line-builder-status{display:block;margin:14px 0;color:#8a4a7c;font-size:13px}.line-builder-status.error{color:#c40000}.line-builder-complete{display:grid;gap:8px;margin-top:14px}.line-builder-complete article{display:flex;align-items:center;gap:12px;border-top:1px solid #ffd1f5;padding:10px 0;color:#111}.line-builder-complete article strong{color:#ff00ff;min-width:48px}.line-builder-type{display:flex;gap:8px;margin-bottom:16px}.line-builder-type button{flex:1;border:1px solid #ff00ff;background:#fff;color:#ff00ff;padding:10px;cursor:pointer;font:inherit}.line-builder-type button.active{background:#ff00ff;color:#fff}@media(max-width:700px){.line-builder-grid{grid-template-columns:1fr}.line-builder-actions{flex-direction:column}.line-builder-actions button{width:100%}}";

document.head.appendChild(lineBuilderStyle);

const lineFileInput =
  document.querySelector("#script-file");

const lineLoadButton =
  loadButton.cloneNode(true);

loadButton.replaceWith(lineLoadButton);

if (lineFileInput) {
  const replacementFileInput =
    lineFileInput.cloneNode(true);

  lineFileInput.replaceWith(replacementFileInput);

  replacementFileInput.addEventListener(
    "change",
    async (event) => {
      const file = event.target.files?.[0];

      if (!file) return;

      input.value = await file.text();
      loadLineByLineScript();
    }
  );
}

const uploadTitle =
  document.querySelector(".upload strong");

const uploadHint =
  document.querySelector(".upload small");

if (uploadTitle) {
  uploadTitle.textContent =
    "Load a script — one line becomes one scene";
}

if (uploadHint) {
  uploadHint.textContent =
    "Choose text, GIF, or video for each line; media searches use the line automatically";
}

input.setAttribute("aria-label", "Script lines");
input.placeholder = "One script line per scene…";
input.value =
  sampleScript.scenes
    .map((scene) => scene.text)
    .join("\n");

let activeLineIndex = 0;
let lineFetchToken = 0;

function parseLineByLineScript() {
  const raw = input.value.trim();

  if (!raw) {
    throw new Error("Add at least one line to your script.");
  }

  let parsed;

  try {
    parsed = JSON.parse(raw);
  } catch (parseError) {
    parsed = null;
  }

  if (parsed && !Array.isArray(parsed.scenes)) {
    throw new Error(
      "A JSON script must contain a scenes array, or paste one scene per line."
    );
  }

  const sourceScenes = parsed
    ? parsed.scenes
    : raw
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((text, index) => ({
          scene_id: String(index + 1),
          text,
          duration_seconds: 0,
          scene_type: "text"
        }));

  if (!sourceScenes.length) {
    throw new Error("Add at least one line to your script.");
  }

  const normalizedScenes = sourceScenes.map(
    (scene, index) => {
      const normalized = {
        ...scene,
        scene_id: String(
          scene.scene_id || index + 1
        ),
        text: String(scene.text || "").trim(),
        duration_seconds:
          Number(scene.duration_seconds) || 0
      };

      if (!normalized.text) {
        throw new Error("Every line needs text.");
      }

      normalized.scene_type =
        ["text", "gif", "video"].includes(
          normalized.scene_type
        )
          ? normalized.scene_type
          : "text";

      normalized.search_query =
        normalized.scene_type === "text"
          ? ""
          : String(
              normalized.search_query ||
              normalized.text
            );

      normalized.pan_region =
        normalized.pan_region === "bottom_50"
          ? "bottom_50"
          : "top_50";

      normalized.pan_direction =
        normalized.pan_direction === "bottom_to_top"
          ? "bottom_to_top"
          : "top_to_bottom";

      normalized.text_position =
        normalized.text_position === "middle"
          ? "middle"
          : "bottom";

      normalized.show_text =
        normalized.scene_type === "text"
          ? true
          : normalized.show_text !== false;

      normalizeColors(normalized);

      return normalized;
    }
  );

  return ensureUniqueProjectId({
    project_id:
      parsed?.project_id ||
      "empire_youtube_channel",
    scenes: normalizedScenes
  });
}

function renderLineBuilder() {
  lineFetchToken += 1;

  const requestToken = lineFetchToken;

  if (activeLineIndex >= currentScript.scenes.length) {
    renderScenes(currentScript);

    const review =
      document.createElement("div");

    review.className =
      "line-builder-actions";

    review.innerHTML =
      '<button type="button" class="primary">Edit lines</button>';

    review
      .querySelector("button")
      .addEventListener("click", () => {
        activeLineIndex = 0;
        renderLineBuilder();
      });

    scenes.prepend(review);
    return;
  }

  const scene =
    currentScript.scenes[activeLineIndex];

  normalizeColors(scene);

  const isMedia =
    scene.scene_type !== "text";

  const provider =
    scene.scene_type === "gif"
      ? "GIPHY"
      : "Pexels";

  scenes.innerHTML = "";

  const builder =
    document.createElement("section");

  builder.className = "line-builder";

  builder.innerHTML =
    "<div class=\"line-builder-head\"><strong>Scene setup</strong><span></span><button type=\"button\" class=\"line-builder-delete\" data-line-delete title=\"Delete this line\">✕ Delete line</button></div><textarea class=\"line-builder-text-input\" data-line-text rows=\"2\"></textarea><div class=\"line-builder-preview-slot\"></div><div class=\"line-builder-type\"><button type=\"button\" data-line-type=\"text\">Text</button><button type=\"button\" data-line-type=\"gif\">GIF</button><button type=\"button\" data-line-type=\"video\">Video</button></div><div class=\"line-builder-search\"><label>Search keyword <input type=\"search\" data-media-search placeholder=\"e.g. confident woman working\" /></label><button type=\"button\" data-search-media>Search media</button></div><div class=\"line-builder-grid\"></div><span class=\"line-builder-status\">Choose Text, GIF, or Video for this line.</span><div class=\"line-builder-actions\"><button type=\"button\" data-line-prev>← Previous line</button><button type=\"button\" class=\"primary\" data-line-next>Next line →</button></div>";

  builder
    .querySelector(".line-builder-preview-slot")
    .innerHTML = scenePreviewHtml(scene, activeLineIndex);

  builder
    .querySelector(".line-builder-head span")
    .textContent =
      "Line " +
      (activeLineIndex + 1) +
      " of " +
      currentScript.scenes.length;

  const textInput =
    builder.querySelector(
      "[data-line-text]"
    );

  textInput.value = scene.text;

  builder
    .querySelector(
      '[data-line-type="' +
        scene.scene_type +
        '"]'
    )
    .classList.add("active");

  const grid =
    builder.querySelector(
      ".line-builder-grid"
    );

  const searchPanel =
    builder.querySelector(
      ".line-builder-search"
    );

  const searchInput =
    builder.querySelector(
      "[data-media-search]"
    );

  const searchButton =
    builder.querySelector(
      "[data-search-media]"
    );

  searchInput.value =
    scene.search_query || scene.text;

  searchButton.textContent =
    "Search " + provider;

  searchPanel.hidden = !isMedia;

  if (isMedia) {
    const panModeLabel =
      document.createElement("label");

    panModeLabel.textContent =
      "Framing";

    panModeLabel.innerHTML +=
      '<select data-pan-mode="' +
      activeLineIndex +
      '"><option value="pan">Pan (animated)</option><option value="static_top">Static — top</option><option value="static_middle">Static — middle</option><option value="static_bottom">Static — bottom</option></select>';

    panModeLabel.querySelector(
      "select"
    ).value = scene.pan_mode || "pan";

    grid.appendChild(panModeLabel);

    const isPanMode = !scene.pan_mode || scene.pan_mode === "pan";

    if (isPanMode) {
    const panRegionLabel =
      document.createElement("label");

    panRegionLabel.textContent =
      "Pan area";

    panRegionLabel.innerHTML +=
      '<select data-pan-region="' +
      activeLineIndex +
      '"><option value="top_50">Top half</option><option value="bottom_50">Bottom half</option></select>';

    panRegionLabel.querySelector(
      "select"
    ).value = scene.pan_region;

    grid.appendChild(panRegionLabel);

    const panDirectionLabel =
      document.createElement("label");

    panDirectionLabel.textContent =
      "Pan motion";

    panDirectionLabel.innerHTML +=
      '<select data-pan-direction="' +
      activeLineIndex +
      '"><option value="top_to_bottom">Top → bottom</option><option value="bottom_to_top">Bottom → top</option></select>';

    panDirectionLabel.querySelector(
      "select"
    ).value = scene.pan_direction;

    grid.appendChild(panDirectionLabel);
    }

    const showTextLabel =
      document.createElement("label");

    showTextLabel.className =
      "scene-control scene-control-checkbox";

    showTextLabel.innerHTML =
      '<input type="checkbox" data-show-text="' +
      activeLineIndex +
      '"> Show text overlay';

    showTextLabel.querySelector(
      "input"
    ).checked = scene.show_text !== false;

    grid.appendChild(showTextLabel);
  }

  const textPositionLabel =
    document.createElement("label");

  textPositionLabel.textContent =
    "Text position";

  textPositionLabel.innerHTML +=
    '<select data-text-position="' +
    activeLineIndex +
    '"><option value="bottom">Bottom</option><option value="middle">Middle</option></select>';

  textPositionLabel.querySelector(
    "select"
  ).value = scene.text_position;

  grid.appendChild(textPositionLabel);

  const durationLabel =
    document.createElement("label");

  durationLabel.textContent =
    "Duration (mm:ss)";

  durationLabel.innerHTML +=
    '<input type="text" data-duration="' +
    activeLineIndex +
    '" />';

  durationLabel.querySelector(
    "input"
  ).value =
    formatDuration(
      scene.duration_seconds
    );

  grid.appendChild(durationLabel);

  const textColorLabel =
    document.createElement("label");

  textColorLabel.textContent =
    "Text color";

  textColorLabel.innerHTML +=
    colorSelectHtml(
      "text-color",
      activeLineIndex,
      scene.text_color
    );

  grid.appendChild(textColorLabel);

  const outlineColorLabel =
    document.createElement("label");

  outlineColorLabel.textContent =
    "Outline color";

  outlineColorLabel.innerHTML +=
    colorSelectHtml(
      "outline-color",
      activeLineIndex,
      scene.outline_color
    );

  grid.appendChild(outlineColorLabel);

  if (!isMedia) {
    const bgColorLabel =
      document.createElement("label");

    bgColorLabel.textContent =
      "Background color";

    bgColorLabel.innerHTML +=
      colorSelectHtml(
        "bg-color",
        activeLineIndex,
        scene.bg_color
      );

    grid.appendChild(bgColorLabel);
  }

  const status =
    builder.querySelector(
      ".line-builder-status"
    );

  const nextButton =
    builder.querySelector(
      "[data-line-next]"
    );

  const previousButton =
    builder.querySelector(
      "[data-line-prev]"
    );

  textInput.addEventListener("change", () => {
    const trimmed = textInput.value.trim();

    if (!trimmed) {
      error.textContent = "A scene's text can't be empty.";
      textInput.value = scene.text;
      return;
    }

    error.textContent = "";
    scene.text = trimmed;
    textInput.value = trimmed;
    updateScenePreview(activeLineIndex);
    scheduleAutosave();
  });

  const deleteLineButton =
    builder.querySelector(
      "[data-line-delete]"
    );

  deleteLineButton.addEventListener("click", () => {
    if (currentScript.scenes.length <= 1) {
      error.textContent = "A script needs at least one scene.";
      return;
    }

    const label = scene.text.slice(0, 60);

    if (!window.confirm(`Delete this line ("${label}")? This can't be undone.`)) {
      return;
    }

    currentScript.scenes.splice(activeLineIndex, 1);

    if (activeLineIndex >= currentScript.scenes.length) {
      activeLineIndex = Math.max(0, currentScript.scenes.length - 1);
    }

    error.textContent = "";
    scheduleAutosave();
    renderLineBuilder();
  });

  const syncNextButton = () => {
    nextButton.disabled =
      isMedia &&
      !(
        scene.selected_video &&
        scene.selected_video.video_files
      );
  };

  searchButton.disabled = isMedia;

  builder
    .querySelectorAll("[data-line-type]")
    .forEach((button) =>
      button.addEventListener(
        "click",
        () => {
          scene.scene_type =
            button.dataset.lineType;

          if (scene.scene_type !== "text") {
            scene.search_query =
              scene.text;
          } else {
            scene.search_query = "";
            delete scene.selected_video;
          }

          renderLineBuilder();
        }
      )
    );

  const searchMedia = async () => {
    const query =
      searchInput.value.trim();

    if (!query) {
      status.textContent =
        "Enter a keyword to search.";

      status.classList.add("error");
      return;
    }

    scene.search_query = query;

    delete scene.selected_video;

    searchButton.disabled = true;
    nextButton.disabled = true;

    status.classList.remove("error");

    status.textContent =
      "Searching " +
      provider +
      " for “" +
      query +
      "”…";

    try {
      const data =
        await loadFootagePreviews(
          {
            project_id:
              currentScript.project_id,
            scenes: [scene]
          },
          false
        );

      if (requestToken !== lineFetchToken) {
        return;
      }

      const candidates =
        data.scenes[0]?.candidates || [];

      status.textContent =
        candidates.length
          ? "Select a " +
            provider +
            " clip below, then continue."
          : "No " +
            provider +
            " results found. Try another keyword.";
    } catch (err) {
      status.classList.add("error");

      status.textContent =
        err instanceof Error
          ? err.message
          : backendUnavailableMessage();
    } finally {
      if (requestToken === lineFetchToken) {
        searchButton.disabled = false;
        syncNextButton();
      }
    }
  };

  searchButton.addEventListener(
    "click",
    searchMedia
  );

  searchInput.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        searchMedia();
      }
    }
  );

  previousButton.disabled =
    activeLineIndex === 0;

  previousButton.addEventListener(
    "click",
    () => {
      if (activeLineIndex > 0) {
        activeLineIndex -= 1;
        renderLineBuilder();
      }
    }
  );

  nextButton.textContent =
    activeLineIndex ===
    currentScript.scenes.length - 1
      ? "Finish scene setup ✓"
      : "Next line →";

  nextButton.addEventListener(
    "click",
    () => {
      activeLineIndex += 1;
      renderLineBuilder();
    }
  );

  scenes.appendChild(builder);

  if (!isMedia) {
    status.textContent =
      "Text scene ready. Choose its position, then continue.";

    syncNextButton();
    return;
  }

  syncNextButton();

  status.textContent =
    `Searching ${
      scene.scene_type === "gif"
        ? "GIPHY"
        : "Pexels"
    } for this line automatically…`;

  loadFootagePreviews(
    {
      project_id:
        currentScript.project_id,
      scenes: [scene]
    },
    true
  )
    .then((data) => {
      if (requestToken !== lineFetchToken) {
        return;
      }

      const footageLabel =
        builder.querySelector(
          ".footage-previews small"
        );

      if (footageLabel) {
        footageLabel.textContent =
          "Select a " +
          provider +
          " clip for this line:";
      }

      searchButton.disabled = false;

      const candidates =
        data.scenes[0]?.candidates || [];

      status.textContent =
        candidates.length
          ? "Select a " +
            provider +
            " clip below, then continue to the next line."
          : "No " +
            provider +
            " results found. Try another keyword.";

      syncNextButton();
    })
    .catch((err) => {
      if (requestToken !== lineFetchToken) {
        return;
      }

      status.classList.add("error");

      status.textContent =
        err instanceof Error
          ? err.message
          : backendUnavailableMessage();

      searchButton.disabled = false;
      nextButton.disabled = true;
    });
}

lineLoadButton.innerHTML =
  "Load script <span>→</span>";

lineLoadButton.addEventListener(
  "click",
  () => {
    try {
      currentScript =
        parseLineByLineScript();

      activeLineIndex = 0;
      error.textContent = "";

      renderLineBuilder();
      scheduleAutosave();
    } catch (err) {
      error.textContent =
        err instanceof Error
          ? err.message
          : "Could not load that script.";
    }
  }
);

scenes.addEventListener(
  "click",
  (event) => {
    if (
      !event.target.closest(
        ".footage-choice"
      )
    ) {
      return;
    }

    window.setTimeout(() => {
      const active =
        currentScript.scenes[
          activeLineIndex
        ];

      const next =
        scenes.querySelector(
          "[data-line-next]"
        );

      if (active && next) {
        next.disabled =
          active.scene_type !== "text" &&
          !(
            active.selected_video &&
            active.selected_video.video_files
          );
      }
    }, 0);
  }
);

renderLineBuilder();
