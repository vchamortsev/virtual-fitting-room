const form = document.querySelector("#tryon-form");
const keyInput = document.querySelector("#api-key");
const modelSelect = document.querySelector("#model");
const modelNote = document.querySelector("#model-note");
const statusEl = document.querySelector("#status");
const warningEl = document.querySelector("#warning");
const resultImg = document.querySelector("#result");
const emptyEl = document.querySelector("#empty");
const progressEl = document.querySelector("#progress");
const progressLabel = document.querySelector("#progress-label");
const shirtEl = document.querySelector("#shirt");
const submitButton = document.querySelector("#submit");

const storedKey = localStorage.getItem("fitting-room-api-key");
if (storedKey) keyInput.value = storedKey;

let catalog = [];
let activeJobId = "";

function headers() {
  return { "X-API-Key": keyInput.value.trim() };
}

function setStatus(text) {
  statusEl.textContent = text;
}

function hideProgress() {
  progressEl.hidden = true;
  shirtEl.classList.remove("is-wait");
  shirtEl.style.setProperty("--pct", "0");
  progressLabel.classList.remove("is-pct");
}

function formatEta(seconds) {
  if (seconds == null) return "";
  if (seconds < 15) return "ещё несколько секунд";
  if (seconds < 60) return `ещё около ${Math.max(15, Math.round(seconds / 10) * 10)} с`;
  const minutes = Math.round(seconds / 60);
  if (minutes <= 1) return "ещё около минуты";
  return `ещё около ${minutes} мин`;
}

function showWait(job) {
  progressEl.hidden = false;
  emptyEl.hidden = true;
  const steps = job.steps || 0;
  const step = job.step || 0;
  const pct = steps ? Math.min(100, Math.round((step / steps) * 100)) : 0;
  shirtEl.style.setProperty("--pct", String(pct / 100));
  if (job.status === "queued" || step <= 0) {
    shirtEl.classList.add("is-wait");
    progressLabel.classList.remove("is-pct");
    const label = job.status === "queued" ? "В очереди" : "Готовлю фото";
    progressLabel.textContent = label;
    setStatus(label);
    return;
  }
  shirtEl.classList.remove("is-wait");
  progressLabel.classList.add("is-pct");
  progressLabel.textContent = `${pct}%`;
  const eta = formatEta(job.eta_seconds);
  setStatus(eta ? `${pct}% · ${eta}` : `${pct}%`);
}

function selectedModel() {
  return catalog.find((item) => item.id === modelSelect.value);
}

function renderModels(payload) {
  catalog = payload.models;
  modelSelect.replaceChildren();
  for (const item of catalog) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.available ? item.title : `${item.title} — недоступна`;
    option.disabled = !item.available;
    modelSelect.append(option);
  }
  const preferred = catalog.find((item) => item.id === payload.default && item.available);
  if (preferred) modelSelect.value = preferred.id;
  showModelNote();
  setStatus("Можно отправлять фото.");
}

function showModelNote() {
  const item = selectedModel();
  if (!item) {
    modelNote.textContent = "";
    return;
  }
  const use = item.commercial_use ? "можно в магазине" : "только некоммерческие проверки";
  modelNote.textContent = `${item.detail} Лицензия: ${item.license}. Видеопамять: ${item.vram}. Использование: ${use}.`;
}

async function loadModels() {
  setStatus("Проверяю модели…");
  const response = await fetch("/v1/models", { headers: headers() });
  if (response.status === 401) {
    setStatus("Ключ не подошёл.");
    return;
  }
  if (!response.ok) {
    setStatus("Не удалось получить список моделей.");
    return;
  }
  renderModels(await response.json());
}

async function showResult(job) {
  hideProgress();
  setStatus("Готово.");
  warningEl.hidden = !job.warning;
  warningEl.textContent = job.warning || "";
  const response = await fetch(job.result_url, { headers: headers() });
  if (!response.ok) {
    setStatus("Картинка не скачалась.");
    return;
  }
  const blob = await response.blob();
  if (resultImg.src.startsWith("blob:")) URL.revokeObjectURL(resultImg.src);
  resultImg.src = URL.createObjectURL(blob);
  resultImg.alt = "Результат примерки";
  resultImg.hidden = false;
  document.querySelector("#sample").hidden = true;
  emptyEl.hidden = true;
}

async function poll(jobId) {
  activeJobId = jobId;
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (activeJobId !== jobId) return;
    const response = await fetch(`/v1/try-on/${jobId}`, { headers: headers() });
    if (!response.ok) {
      hideProgress();
      setStatus("Не удалось прочитать статус.");
      return;
    }
    const job = await response.json();
    if (job.status === "succeeded") {
      await showResult(job);
      return;
    }
    if (job.status === "failed") {
      hideProgress();
      setStatus(job.error || "Примерка не выполнилась.");
      return;
    }
    showWait(job);
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  hideProgress();
  setStatus(`Задание ${jobId} ещё считается. Обновите страницу позже и проверьте журнал сервера.`);
}

modelSelect.addEventListener("change", showModelNote);
keyInput.addEventListener("change", () => {
  localStorage.setItem("fitting-room-api-key", keyInput.value.trim());
  loadModels().catch(() => setStatus("Сервер не ответил."));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  warningEl.hidden = true;
  try {
    const data = new FormData(form);
    data.delete("api_key");
    const garmentFile = form.elements.garment_image.files[0];
    const garmentUrl = form.elements.garment_url.value.trim();
    if (!garmentFile) data.delete("garment_image");
    if (!garmentFile && !garmentUrl) {
      setStatus("Добавьте фото вещи или ссылку на страницу товара.");
      submitButton.disabled = false;
      return;
    }
    resultImg.hidden = true;
    document.querySelector("#sample").hidden = false;
    emptyEl.hidden = false;
    if (!form.elements.segmentation_free.checked) data.set("segmentation_free", "false");
    setStatus(garmentFile ? "Отправляю…" : "Открываю страницу товара…");
    const response = await fetch("/v1/try-on", {
      method: "POST",
      headers: headers(),
      body: data,
    });
    const payload = await response.json();
    if (!response.ok && response.status !== 202) {
      hideProgress();
      setStatus(payload.detail || "Запрос отклонён.");
      return;
    }
    if (payload.status === "succeeded") {
      await showResult(payload);
      return;
    }
    if (payload.status === "failed") {
      hideProgress();
      setStatus(payload.error || "Примерка не выполнилась.");
      return;
    }
    showWait(payload);
    await poll(payload.id);
  } catch (error) {
    hideProgress();
    setStatus("Сеть недоступна.");
  } finally {
    submitButton.disabled = false;
  }
});

function showFile(input, drop, file) {
  const thumb = drop.querySelector(".thumb");
  if (!file) {
    drop.classList.remove("has-file");
    thumb.removeAttribute("src");
    return;
  }
  if (thumb.src.startsWith("blob:")) URL.revokeObjectURL(thumb.src);
  thumb.src = URL.createObjectURL(file);
  drop.classList.add("has-file");
}

function bindPreview(inputId, dropId) {
  const input = document.querySelector(inputId);
  const drop = document.querySelector(dropId);
  input.addEventListener("change", () => showFile(input, drop, input.files[0]));
  drop.addEventListener("dragenter", (event) => {
    event.preventDefault();
    drop.classList.add("is-dragover");
  });
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  drop.addEventListener("dragleave", (event) => {
    if (drop.contains(event.relatedTarget)) return;
    drop.classList.remove("is-dragover");
  });
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("is-dragover");
    const file = [...(event.dataTransfer?.files || [])].find((item) => item.type.startsWith("image/"));
    if (!file) {
      setStatus("Перетащите фотографию.");
      return;
    }
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    showFile(input, drop, file);
  });
}

bindPreview("#person", "#person-drop");
bindPreview("#garment", "#garment-drop");

loadModels().catch(() => setStatus("Сервер не ответил."));
