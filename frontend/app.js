(function mountEmpireEditor() {\n  if (document.getElementById('script-editor')) return;\n  document.title = 'Empire Scene Editor';\n  document.body.innerHTML = [\n    '<main class="app-shell">',\n    '<header class="topbar"><a class="brand" href="/"><span class="brand-mark">E</span><span class="brand-wordmark">EMPIRE<small>SCENE EDITOR</small></span></a><div class="project-name"><span class="status-dot"></span><span>One idea, three minutes</span><span class="divider"></span><span class="muted">Draft</span></div><div class="top-actions"><span id="save-state" class="save-state"><span class="save-dot"></span> SAVED LOCALLY</span><button id="preview-toggle" class="button button-light" type="button">▶ Preview</button><button id="export-button" class="button button-coral" type="button">↗ Export</button><span class="avatar">AL</span></div></header>',\n    '<div class="workspace">',\n    '<aside class="script-column"><div class="column-heading"><div><span class="heading-icon">T</span><span class="heading-label">SCRIPT</span><span id="scene-count" class="count-pill">4 SCENES</span></div><span class="plain-label">Plain text ⌄</span></div><div class="script-card"><div class="selection-hint"><span class="cursor-icon">↗</span><span>Highlight a thought to make it a new scene. Your words stay yours.</span></div><div id="script-editor" class="script-editor" contenteditable="true" role="textbox" aria-label="Script text"></div><div class="selection-bar"><button id="make-scene-button" class="button button-coral button-small" type="button" disabled>Make new scene ↗</button><button id="add-paragraph" class="text-button" type="button">+ Add thought</button></div></div><div class="script-footer"><span id="word-count">0 words</span><span id="time-count">Approx. 00:20</span></div></aside>',\n    '<section class="canvas-column"><div class="canvas-toolbar"><div><span class="mono-label">CANVAS / 9:16</span><span id="canvas-time" class="mono-label muted">00:01 / 00:20</span></div><button class="round-button" id="more-button" type="button">•••</button></div><div class="canvas-stage"><div id="video-preview" class="video-preview"><div class="preview-topline"><span>EMPIRE / 001</span><span id="preview-category">VIDEO / MORNING</span></div><div id="preview-content" class="preview-content"><h2 id="preview-text"></h2><span class="preview-caption">KEEP GOING</span></div><div class="preview-bottomline"><span>A NOTE ON MAKING</span><span id="preview-number">01</span></div><button id="preview-play" class="preview-play" type="button">▶</button></div><div class="canvas-meta"><span><i class="meta-square"></i>1080 × 1920</span><span><i class="meta-wave"></i>Voiceover off</span></div></div><div class="scene-strip-heading"><span>SCENE STRIP <b id="strip-count">4 / 8</b></span><span class="muted">Drag to reorder · <span id="total-time">00:20 total</span></span></div><div id="scene-strip" class="scene-strip"></div></section>',\n    '<aside class="inspector-column"><div id="inspector" class="inspector-content"></div><div id="save-toast" class="save-toast">✓ Scene changes saved</div></aside>',\n    '</div><div id="toast" class="toast" role="status" aria-live="polite"></div></main>'\n  ].join('');\n})();\nconst initialParagraphs = [
    "The best ideas are usually the ones we almost talk ourselves out of.",
    "We wait for confidence to arrive before we make the thing.",
    "But confidence is not a prerequisite. It is the receipt.",
    "Publish the first version. Let the next one teach you how."
    ];

    const localVideos = [
    { id: "local-1", title: "Hands on a concrete table", meta: "portrait · 4K", duration: 4, gradient: "linear-gradient(135deg, #1b2538, #d06452)" },
    { id: "local-2", title: "Morning light through glass", meta: "portrait · 1080p", duration: 4, gradient: "linear-gradient(135deg, #2a3344, #b47b67)" },
    { id: "local-3", title: "Person walking through a room", meta: "portrait · 4K", duration: 4, gradient: "linear-gradient(135deg, #172636, #496f78)" }
    ];
    const localGifs = [
    { id: "gif-1", title: "Tiny spark", gradient: "radial-gradient(circle at 50% 42%, #ffd4a5 0 5%, transparent 6%), linear-gradient(135deg, #ff8f72, #493c63)" },
    { id: "gif-2", title: "Soft loop", gradient: "radial-gradient(circle at 62% 38%, #b8f1dd 0 8%, transparent 9%), linear-gradient(135deg, #183b4f, #78a89c)" },
    { id: "gif-3", title: "Electric line", gradient: "linear-gradient(135deg, #1c2030 40%, #f2b370 41% 45%, #1c2030 46% 52%, #ed7a6f 53% 57%, #1c2030 58%)" }
    ];
    const iconChoices = ["✦", "↗", "◎", "✳", "◌", "◆", "⌁", "✺"];
    const sceneColors = ["coral", "teal", "mustard", "navy"];
    let scenes = initialParagraphs.map((text, index) => ({
    id: String(index + 1),
    text,
    duration: 5,
    mediaType: index === 0 ? "video" : index === 1 ? "icon" : index === 2 ? "gif" : "previous",
    searchQuery: index === 0 ? "quiet creative process" : text,
    icon: iconChoices[index + 1],
    overlay: index === 3 ? "icon" : "text",
    selectedVideo: index === 0 ? localVideos[0] : null,
    selectedGif: index === 2 ? localGifs[1] : null,
    color: sceneColors[index % sceneColors.length],
    videoResults: localVideos,
    gifResults: localGifs,
    searchNotice: ""
    }));
    let activeSceneId = "1";
    let pendingSelection = "";
    let isPlaying = false;
    let previewTimer = null;

    const scriptEditor = document.querySelector("#script-editor");
    const makeSceneButton = document.querySelector("#make-scene-button");
    const inspector = document.querySelector("#inspector");
    const sceneStrip = document.querySelector("#scene-strip");
    const toast = document.querySelector("#toast");

    function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character];
    });
    }
    function activeScene() { return scenes.find(function (scene) { return scene.id === activeSceneId; }) || scenes[0]; }
    function paragraphsToHtml(text) {
    return text.split(/
{2,}/).map(function (paragraph) { return "<p>" + escapeHtml(paragraph.trim()) + "</p>"; }).filter(Boolean).join("");
    }
    function syncEditorText() {
    const text = Array.from(scriptEditor.querySelectorAll("p")).map(function (paragraph) { return paragraph.innerText.trim(); }).filter(Boolean).join("

");
    if (text) localStorage.setItem("empire-script-text", text);
    }
    function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(function () { toast.classList.remove("show"); }, 2400);
    }
    function totalDuration() { return scenes.reduce(function (sum, scene) { return sum + Number(scene.duration || 5); }, 0); }
    function updateCounts() {
    const words = scenes.map(function (scene) { return scene.text; }).join(" ").trim().split(/s+/).filter(Boolean).length;
    const total = totalDuration();
    document.querySelector("#scene-count").textContent = scenes.length + " SCENES";
    document.querySelector("#strip-count").textContent = scenes.length + " / 8";
    document.querySelector("#word-count").textContent = words + " words";
    document.querySelector("#time-count").textContent = "Approx. " + String(total).padStart(2, "0") + ":00";
    document.querySelector("#total-time").textContent = "00:" + String(total).padStart(2, "0") + " total";
    document.querySelector("#canvas-time").textContent = "00:01 / 00:" + String(total).padStart(2, "0");
    }
    function saveState() {
    try {
      localStorage.setItem("empire-scenes", JSON.stringify(scenes));
      document.querySelector("#save-state").innerHTML = '<span class="save-dot"></span> SAVED LOCALLY';
    } catch (error) { document.querySelector("#save-state").textContent = " SAVED FOR THIS SESSION"; }
    }
    function sceneLabel(scene) {
    return scene.mediaType === "previous" ? "PREVIOUS" : scene.mediaType.toUpperCase();
    }
    function sceneThumbStyle(scene) {
    if (scene.mediaType === "video" && scene.selectedVideo && scene.selectedVideo.image) return "background-image:url('" + scene.selectedVideo.image + "')";
    if (scene.mediaType === "icon") return "background:" + (scene.color === "teal" ? "linear-gradient(135deg,#1f6f73,#b9e4d7)" : "linear-gradient(135deg,#eb796b,#473e60)");
    if (scene.mediaType === "gif") return "background:" + (scene.selectedGif?.gradient || "linear-gradient(135deg,#1b2638,#ef8871)");
    return "background:linear-gradient(135deg,#17253a,#6a8f8d)";
    }
    function renderSceneStrip() {
    sceneStrip.innerHTML = scenes.map(function (scene, index) {
      const activeClass = scene.id === activeSceneId ? " active" : "";
      return '<button type="button" class="strip-card' + activeClass + '" data-scene-id="' + scene.id + '" style="' + sceneThumbStyle(scene) + '">' +
        '<span class="strip-card-top"><b>' + String(index + 1).padStart(2, "0") + '</b><span>' + scene.duration + 's</span></span>' +
        '<span class="strip-card-bottom"><strong>' + escapeHtml(sceneLabel(scene)) + '</strong><small>' + escapeHtml(scene.text.slice(0, 24)) + (scene.text.length > 24 ? "…" : "") + '</small></span>' +
        '</button>';
    }).join("") + '<button type="button" class="strip-add" id="strip-add">+<small>Add scene</small></button>';
    }
    function renderScript() {
    const paragraphs = scenes.map(function (scene) {
      const isActive = scene.id === activeSceneId ? " active-paragraph" : "";
      return '<p class="' + isActive.trim() + '" data-scene-id="' + scene.id + '">' + escapeHtml(scene.text) + '</p>';
    }).join("");
    scriptEditor.innerHTML = paragraphs;
    }
    function previewBackground(scene) {
    if (!scene) return "linear-gradient(135deg,#18243a,#d56e5f)";
    if (scene.mediaType === "video" && scene.selectedVideo && scene.selectedVideo.image) return "linear-gradient(135deg,rgba(20,28,45,.35),rgba(205,91,75,.75)),url('" + scene.selectedVideo.image + "') center/cover";
    if (scene.mediaType === "icon") return scene.color === "teal" ? "radial-gradient(circle at 70% 22%,#f4cfaa 0 5%,transparent 6%),linear-gradient(135deg,#17535d,#a1d0bf)" : "radial-gradient(circle at 72% 25%,#ffc17f 0 5%,transparent 6%),linear-gradient(135deg,#1b293e,#d26f60)";
    if (scene.mediaType === "gif") return scene.selectedGif?.gradient || "linear-gradient(135deg,#263d54,#dd886e)";
    const previous = scenes[Math.max(0, scenes.indexOf(scene) - 1)];
    return previous ? previewBackground(previous) : "linear-gradient(135deg,#1b293f,#d26f60)";
    }
    function renderPreview() {
    const scene = activeScene();
    if (!scene) return;
    document.querySelector("#video-preview").style.background = previewBackground(scene);
    document.querySelector("#preview-text").textContent = scene.text;
    document.querySelector("#preview-number").textContent = String(scenes.indexOf(scene) + 1).padStart(2, "0");
    document.querySelector("#preview-category").textContent = sceneLabel(scene) + " / " + (scene.mediaType === "video" ? "MORNING" : "SCENE " + scene.id);
    const previewContent = document.querySelector("#preview-content");
    previewContent.classList.toggle("icon-preview", scene.mediaType === "icon");
    previewContent.classList.toggle("gif-preview", scene.mediaType === "gif");
    previewContent.classList.toggle("previous-preview", scene.mediaType === "previous");
    const oldIcon = previewContent.querySelector(".preview-icon");
    if (oldIcon) oldIcon.remove();
    if (scene.mediaType === "icon" || (scene.mediaType === "previous" && scene.overlay === "icon")) {
      const icon = document.createElement("span");
      icon.className = "preview-icon";
      icon.textContent = scene.icon || "✦";
      previewContent.insertBefore(icon, previewContent.firstChild);
    }
    const oldGif = previewContent.querySelector(".preview-gif");
    if (oldGif) oldGif.remove();
    if (scene.mediaType === "gif" || (scene.mediaType === "previous" && scene.overlay === "gif")) {
      const gif = document.createElement("span");
      gif.className = "preview-gif";
      gif.textContent = "GIF";
      previewContent.insertBefore(gif, previewContent.firstChild);
    }
    document.querySelector("#preview-caption");
    }
    function mediaButton(scene, type, title, note, icon) {
    return '<button type="button" class="media-choice ' + (scene.mediaType === type ? "selected" : "") + '" data-media-type="' + type + '"><span class="media-icon">' + icon + '</span><span><b>' + title + '</b><small>' + note + '</small></span></button>';
    }
    function renderVideoPicker(scene) {
    const results = scene.videoResults || localVideos;
    return '<div class="picker-section"><div class="picker-heading"><span>FIND FOOTAGE</span><span class="provider-chip">PEXELS</span></div>' +
      '<div class="search-row"><input id="video-query" value="' + escapeHtml(scene.searchQuery || "quiet creative process") + '" aria-label="Search Pexels videos" /><button id="video-search" type="button" aria-label="Search Pexels">⌕</button></div>' +
      (scene.searchNotice ? '<p class="picker-notice">' + escapeHtml(scene.searchNotice) + '</p>' : '') +
      '<div class="video-results">' + results.map(function (video) {
        const selected = scene.selectedVideo && scene.selectedVideo.id === video.id ? " selected" : "";
        return '<button type="button" class="video-result' + selected + '" data-video-id="' + escapeHtml(video.id) + '"><span class="result-image" style="background:' + (video.gradient || "linear-gradient(135deg,#202a3f,#cc786c)") + (video.image ? ";background-image:url('" + escapeHtml(video.image) + "')" : "") + '"><i>' + (video.duration || 4) + 's</i></span><span><b>' + escapeHtml(video.title || "Pexels footage") + '</b><small>' + escapeHtml(video.meta || "portrait") + '</small></span></button>';
      }).join("") + '</div><span class="powered">Powered by Pexels <b>↗</b></span></div>';
    }
    function renderIconPicker(scene) {
    return '<div class="picker-section"><div class="picker-heading"><span>CHOOSE AN ICON</span><span class="provider-chip warm">SYMBOL</span></div><div class="icon-grid">' + iconChoices.map(function (icon) {
      return '<button type="button" class="icon-choice ' + (scene.icon === icon ? "selected" : "") + '" data-icon="' + icon + '">' + icon + '</button>';
    }).join("") + '</div><p class="field-note">Pick a mark that reinforces the feeling of this thought.</p></div>';
    }
    function renderGifPicker(scene) {
    const results = scene.gifResults || localGifs;
    return '<div class="picker-section"><div class="picker-heading"><span>FIND A LOOP</span><span class="provider-chip violet">GIF</span></div><div class="search-row"><input id="gif-query" placeholder="Search loops" value="" aria-label="Search GIFs" /><button id="gif-search" type="button" aria-label="Search GIFs">⌕</button></div><div class="gif-results">' + results.map(function (gif) {
      const selected = scene.selectedGif && scene.selectedGif.id === gif.id ? " selected" : "";
      return '<button type="button" class="gif-result' + selected + '" data-gif-id="' + gif.id + '" style="background:' + gif.gradient + '"><span>' + escapeHtml(gif.title) + '</span><b>GIF</b></button>';
    }).join("") + '</div><label class="url-field">Or paste a GIF URL<input id="custom-gif" type="url" placeholder="https://…" /></label><p class="field-note">Loops sit above the scene while the text remains readable.</p></div>';
    }
    function renderPreviousPicker(scene) {
    return '<div class="picker-section"><div class="picker-heading"><span>REUSE THIS VISUAL</span><span class="provider-chip">PREVIOUS</span></div><div class="reuse-card"><span class="reuse-thumb" style="' + sceneThumbStyle(scenes[Math.max(0, scenes.indexOf(scene) - 1)]) + '"></span><div><b>Scene ' + String(Math.max(1, scenes.indexOf(scene))).padStart(2, "0") + ' background</b><small>Keep the visual language moving</small></div></div><div class="overlay-heading">ADD AN OVERLAY</div><div class="overlay-options">' + ["text", "icon", "gif"].map(function (option) { return '<button type="button" class="overlay-choice ' + (scene.overlay === option ? "selected" : "") + '" data-overlay="' + option + '">' + option.charAt(0).toUpperCase() + option.slice(1) + '</button>'; }).join("") + '</div><p class="field-note">Reuse the previous background and change only what sits on top.</p></div>';
    }
    function renderInspector() {
    const scene = activeScene();
    if (!scene) return;
    let picker = scene.mediaType === "video" ? renderVideoPicker(scene) : scene.mediaType === "icon" ? renderIconPicker(scene) : scene.mediaType === "gif" ? renderGifPicker(scene) : renderPreviousPicker(scene);
    inspector.innerHTML = '<div class="inspector-header"><div><span class="inspector-kicker">SCENE ' + String(scenes.indexOf(scene) + 1).padStart(2, "0") + '</span><h2>' + escapeHtml(scene.text.split(" ").slice(0, 4).join(" ")) + (scene.text.split(" ").length > 4 ? "…" : "") + '</h2></div><button class="round-button" id="scene-menu" type="button">•••</button></div><div class="inspector-tabs"><span class="active">MEDIA</span><span>TYPE</span></div><div class="treatment-label">VISUAL TREATMENT</div><div class="media-choices">' + mediaButton(scene, "video", "Video", "Pexels footage", "▦") + mediaButton(scene, "icon", "Icon", "Symbolic mark", "✦") + mediaButton(scene, "gif", "GIF", "Looping moment", "▣") + mediaButton(scene, "previous", "Previous", "Reuse visual", "◫") + '</div>' + picker + '<div class="duration-control"><label for="duration">SCENE LENGTH</label><div><input id="duration" type="range" min="2" max="12" value="' + scene.duration + '" /><output id="duration-value">' + scene.duration + ' sec</output></div></div>';
    }
    function renderAll() {
    renderScript();
    renderSceneStrip();
    renderPreview();
    renderInspector();
    updateCounts();
    saveState();
    }
    function setActive(id) {
    activeSceneId = String(id);
    pendingSelection = "";
    makeSceneButton.disabled = true;
    renderAll();
    }
    function splitSelection() {
    const selected = pendingSelection.trim();
    if (!selected) return;
    let didSplit = false;
    const nextScenes = [];
    scenes.forEach(function (scene) {
      if (!didSplit && scene.text.includes(selected)) {
        const pieces = scene.text.split(selected);
        if (pieces[0].trim()) nextScenes.push(Object.assign({}, scene, { id: scene.id + "a", text: pieces[0].trim() }));
        const newScene = Object.assign({}, scene, { id: scene.id + "-new-" + Date.now(), text: selected, mediaType: "video", selectedVideo: localVideos[0], videoResults: localVideos });
        nextScenes.push(newScene);
        if (pieces.slice(1).join(selected).trim()) nextScenes.push(Object.assign({}, scene, { id: scene.id + "b", text: pieces.slice(1).join(selected).trim() }));
        activeSceneId = newScene.id;
        didSplit = true;
      } else nextScenes.push(scene);
    });
    if (!didSplit) {
      const newScene = { id: "new-" + Date.now(), text: selected, duration: 5, mediaType: "video", searchQuery: selected, icon: "✦", overlay: "text", selectedVideo: localVideos[0], selectedGif: null, color: "coral", videoResults: localVideos, gifResults: localGifs, searchNotice: "" };
      scenes.push(newScene);
      activeSceneId = newScene.id;
    } else scenes = nextScenes;
    pendingSelection = "";
    renderAll();
    notify("New scene created from your highlight");
    }
    async function searchPexels() {
    const scene = activeScene();
    const input = document.querySelector("#video-query");
    const query = input ? input.value.trim() : scene.text;
    if (!query) return;
    scene.searchQuery = query;
    scene.searchNotice = "Searching Pexels…";
    renderInspector();
    try {
      const response = await fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: "empire_visual_editor", scenes: [{ scene_id: scene.id, text: query, duration_seconds: scene.duration, scene_type: "video", search_query: query }] }) });
      if (!response.ok) throw new Error("Pexels is not connected");
      const data = await response.json();
      const found = data.scenes && data.scenes[0] && data.scenes[0].candidates ? data.scenes[0].candidates : [];
      if (!found.length) throw new Error("No Pexels footage found");
      scene.videoResults = found.map(function (video, index) { return { id: String(video.id), title: "Pexels result " + (index + 1), meta: "portrait · Pexels", duration: video.duration || 4, image: video.image, preview_url: video.preview_url, video_files: video.video_files }; });
      scene.selectedVideo = scene.videoResults[0];
      scene.searchNotice = "Live Pexels results";
    } catch (error) {
      scene.videoResults = localVideos;
      scene.selectedVideo = scene.videoResults[0];
      scene.searchNotice = "Showing studio samples. Add PEXELS_API_KEY for live results.";
    }
    renderInspector();
    renderSceneStrip();
    renderPreview();
    saveState();
    }
    function addThought() {
    const id = "new-" + Date.now();
    const scene = { id, text: "Write the next thought here.", duration: 5, mediaType: "video", searchQuery: "creative process", icon: "✦", overlay: "text", selectedVideo: localVideos[0], selectedGif: null, color: "teal", videoResults: localVideos, gifResults: localGifs, searchNotice: "" };
    scenes.push(scene);
    activeSceneId = id;
    renderAll();
    const last = scriptEditor.querySelector("p:last-child");
    if (last) { last.focus(); const range = document.createRange(); range.selectNodeContents(last); range.collapse(false); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }
    }
    function togglePlayback() {
    isPlaying = !isPlaying;
    document.querySelector("#preview-play").textContent = isPlaying ? "Ⅱ" : "▶";
    document.querySelector("#preview-toggle").innerHTML = isPlaying ? '<span class="button-icon">Ⅱ</span> Pause' : '<span class="button-icon">▶</span> Preview';
    document.querySelector("#video-preview").classList.toggle("playing", isPlaying);
    if (isPlaying) {
      let index = scenes.findIndex(function (scene) { return scene.id === activeSceneId; });
      previewTimer = window.setInterval(function () { index = (index + 1) % scenes.length; setActive(scenes[index].id); }, 2600);
    } else { window.clearInterval(previewTimer); }
    }
    async function exportVideo() {
    const button = document.querySelector("#export-button");
    button.disabled = true;
    button.innerHTML = '<span class="button-icon">…</span> Preparing';
    const payload = { project_id: "empire_visual_editor", language: "en", scenes: scenes.map(function (scene) { return { scene_id: scene.id, text: scene.text, duration_seconds: scene.duration, media_type: scene.mediaType, scene_type: scene.mediaType === "video" ? "video" : "text", search_query: scene.searchQuery, selected_video: scene.selectedVideo && scene.selectedVideo.video_files ? scene.selectedVideo : undefined, icon: scene.icon, selected_gif: scene.selectedGif && scene.selectedGif.url ? scene.selectedGif.url : undefined, overlay: scene.overlay }; }) };
    try {
      const response = await fetch("/api/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error("The renderer could not start");
      const job = await response.json();
      notify("Render started — your video will download when ready");
      let state = { status: "queued" };
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise(function (resolve) { window.setTimeout(resolve, 2000); });
        const statusResponse = await fetch(job.status_url);
        state = await statusResponse.json();
        if (state.status === "failed") throw new Error(state.error || "Render failed");
        if (state.status === "complete") break;
      }
      if (state.status !== "complete") throw new Error("Render is taking longer than expected");
      const download = await fetch(job.download_url);
      if (!download.ok) throw new Error("The video download failed");
      const link = document.createElement("a"); link.href = URL.createObjectURL(await download.blob()); link.download = "empire-visual-video.mp4"; link.click();
      notify("Your video is ready");
    } catch (error) { notify(error.message || "Export failed"); }
    button.disabled = false;
    button.innerHTML = '<span class="button-icon">↗</span> Export';
    }

    document.addEventListener("selectionchange", function () {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !scriptEditor.contains(selection.anchorNode)) {
      pendingSelection = "";
      makeSceneButton.disabled = true;
      return;
    }
    pendingSelection = selection.toString().trim();
    makeSceneButton.disabled = !pendingSelection;
    });
    scriptEditor.addEventListener("input", function () { syncEditorText(); document.querySelector("#save-state").innerHTML = '<span class="save-dot"></span> UNSAVED CHANGES'; });
    scriptEditor.addEventListener("click", function (event) { const paragraph = event.target.closest("p[data-scene-id]"); if (paragraph) setActive(paragraph.dataset.sceneId); });
    makeSceneButton.addEventListener("click", splitSelection);
    document.querySelector("#add-paragraph").addEventListener("click", addThought);
    document.querySelector("#preview-play").addEventListener("click", togglePlayback);
    document.querySelector("#preview-toggle").addEventListener("click", togglePlayback);
    document.querySelector("#export-button").addEventListener("click", exportVideo);
    sceneStrip.addEventListener("click", function (event) { const card = event.target.closest("[data-scene-id]"); if (card) setActive(card.dataset.sceneId); if (event.target.closest("#strip-add")) addThought(); });
    inspector.addEventListener("click", function (event) {
    const scene = activeScene();
    const mediaButton = event.target.closest("[data-media-type]");
    if (mediaButton) { scene.mediaType = mediaButton.dataset.mediaType; renderAll(); return; }
    const videoButton = event.target.closest("[data-video-id]");
    if (videoButton) { scene.selectedVideo = (scene.videoResults || localVideos).find(function (video) { return String(video.id) === videoButton.dataset.videoId; }) || scene.selectedVideo; renderAll(); return; }
    const iconButton = event.target.closest("[data-icon]");
    if (iconButton) { scene.icon = iconButton.dataset.icon; renderAll(); return; }
    const gifButton = event.target.closest("[data-gif-id]");
    if (gifButton) { scene.selectedGif = (scene.gifResults || localGifs).find(function (gif) { return gif.id === gifButton.dataset.gifId; }) || scene.selectedGif; renderAll(); return; }
    const overlayButton = event.target.closest("[data-overlay]");
    if (overlayButton) { scene.overlay = overlayButton.dataset.overlay; renderAll(); return; }
    if (event.target.closest("#video-search")) searchPexels();
    if (event.target.closest("#gif-search")) { scene.searchNotice = "GIF search is ready for a provider connection."; renderInspector(); }
    });
    inspector.addEventListener("input", function (event) {
    const scene = activeScene();
    if (event.target.id === "duration") { scene.duration = Number(event.target.value); document.querySelector("#duration-value").textContent = scene.duration + " sec"; updateCounts(); saveState(); }
    if (event.target.id === "video-query") scene.searchQuery = event.target.value;
    });
    scriptEditor.innerHTML = paragraphsToHtml(initialParagraphs.join("

"));
    renderAll();
    