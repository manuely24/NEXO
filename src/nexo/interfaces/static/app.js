const form = document.querySelector("#run-form");
const message = document.querySelector("#message");
const dataClass = document.querySelector("#data-class");
const actionsList = document.querySelector("#actions-list");
const actionCount = document.querySelector("#action-count");
const pendingList = document.querySelector("#pending-list");
const upcomingDays = document.querySelector("#upcoming-days");
const auditList = document.querySelector("#audit-list");
const connection = document.querySelector("#connection-status");
const toast = document.querySelector("#toast");
const conversationLog = document.querySelector("#conversation-log");
const voiceButton = document.querySelector("#voice-button");
const voiceOutput = document.querySelector("#voice-output");
const voiceState = document.querySelector("#voice-state");
const pendingCount = document.querySelector("#pending-count");

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "assistant" ? "NEXO" : "TÚ";
  const time = document.createElement("time");
  time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  label.append(time);
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.append(label, paragraph);
  conversationLog.append(article);
  while (conversationLog.children.length > 21) conversationLog.children[1].remove();
  conversationLog.scrollTop = conversationLog.scrollHeight;
  if (role === "assistant" && voiceOutput.checked && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}

function updateActionSummary() {
  const items = [...actionsList.querySelectorAll(".action-item")];
  actionCount.textContent = String(items.length);
  pendingCount.textContent = String(items.filter((item) => item.dataset.state === "pending_approval").length);
}

const labels = {
  pending_approval: "Requiere aprobación",
  succeeded: "Verificada",
  denied: "Denegada",
  failed: "Falló",
  running: "En ejecución",
};

function showToast(text) {
  toast.textContent = text;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function addAction(action) {
  if (actionsList.querySelector(`[data-id="${CSS.escape(action.id)}"]`)) return;
  actionsList.querySelector(".empty-state")?.remove();
  const article = document.createElement("article");
  article.className = "action-item";
  article.dataset.id = action.id;
  article.dataset.state = action.status;

  const top = document.createElement("div");
  top.className = "action-top";
  const text = document.createElement("div");
  const tool = document.createElement("p");
  tool.className = "action-tool";
  tool.textContent = action.tool;
  const title = document.createElement("h3");
  title.textContent = action.expected_outcome;
  text.append(tool, title);
  const state = document.createElement("span");
  state.className = `state-label ${action.status === "pending_approval" ? "pending" : action.status}`;
  state.textContent = labels[action.status] ?? action.status;
  top.append(text, state);
  article.append(top);

  if (action.reason || action.error) {
    const reason = document.createElement("p");
    reason.className = "action-reason";
    reason.textContent = action.reason ?? action.error;
    article.append(reason);
  }
  if (action.output) {
    const output = document.createElement("pre");
    output.className = "action-output";
    output.textContent = action.output;
    article.append(output);
  }
  if (action.status === "pending_approval") {
    const controls = document.createElement("div");
    controls.className = "approval-controls";
    controls.append(
      decisionButton(action.id, false, "Denegar", "button button-deny"),
      decisionButton(action.id, true, "Aprobar", "button button-approve"),
    );
    article.append(controls);
  }
  actionsList.prepend(article);
  updateActionSummary();
}

async function loadPendingActions() {
  try {
    const response = await fetch("/api/actions/pending");
    const actions = await response.json();
    if (!response.ok) return;
    const pendingIds = new Set(actions.map((action) => action.id));
    for (const action of actions) addAction(action);
    actionsList.querySelectorAll('.action-item[data-state="pending_approval"]').forEach((item) => {
      if (!pendingIds.has(item.dataset.id)) item.remove();
    });
    updateActionSummary();
  } catch {
    // El servidor puede estar reiniciándose; el siguiente sondeo volverá a intentarlo.
  }
}

function decisionButton(id, approved, label, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const response = await fetch(`/api/actions/${encodeURIComponent(id)}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "No se pudo registrar la decisión");
      const article = actionsList.querySelector(`[data-id="${CSS.escape(id)}"]`);
      article?.remove();
      addAction({
        ...result,
        tool: article?.querySelector(".action-tool")?.textContent ?? "acción",
        expected_outcome: approved ? "Ejecución y verificación" : "Acción denegada",
      });
      showToast(approved ? "Acción aprobada" : "Acción denegada");
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
    }
  });
  return button;
}

async function loadPending() {
  pendingList.replaceChildren(Object.assign(document.createElement("li"), {
    className: "empty-state",
    textContent: "Actualizando…",
  }));
  try {
    const response = await fetch(`/api/pending?upcoming=${encodeURIComponent(upcomingDays.value || 7)}`);
    const tasks = await response.json();
    if (!response.ok) throw new Error(tasks.detail ?? "No se pudieron cargar las tareas");
    pendingList.replaceChildren();
    if (!tasks.length) {
      pendingList.append(Object.assign(document.createElement("li"), {
        className: "empty-state",
        textContent: "No hay entregas en este periodo.",
      }));
      return;
    }
    for (const task of tasks) {
      const item = document.createElement("li");
      item.className = "pending-item";
      const date = document.createElement("span");
      date.className = "pending-date";
      date.textContent = task.due_date;
      const title = document.createElement("span");
      title.className = "pending-title";
      title.textContent = task.title;
      const subject = document.createElement("span");
      subject.className = "pending-subject";
      subject.textContent = `${task.subject} · ${task.status}`;
      item.append(date, title, subject);
      pendingList.append(item);
    }
  } catch (error) {
    pendingList.replaceChildren(Object.assign(document.createElement("li"), {
      className: "empty-state",
      textContent: error.message,
    }));
  }
}

function connectAudit() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
  socket.addEventListener("open", () => {
    connection.classList.add("online");
    connection.lastElementChild.textContent = "Nexo local activo";
  });
  socket.addEventListener("close", () => {
    connection.classList.remove("online");
    connection.lastElementChild.textContent = "Reconectando";
    window.setTimeout(connectAudit, 1800);
  });
  socket.addEventListener("message", (messageEvent) => {
    const messageData = JSON.parse(messageEvent.data);
    if (messageData.type !== "event") return;
    auditList.querySelector(".empty-state")?.remove();
    const event = messageData.event;
    const item = document.createElement("li");
    item.className = "audit-entry";
    const timestamp = document.createElement("time");
    timestamp.className = "audit-time";
    timestamp.textContent = new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const detail = document.createElement("span");
    detail.className = "audit-kind";
    detail.textContent = event.kind.replaceAll("_", " ");
    const payload = document.createElement("span");
    payload.className = "audit-detail";
    payload.textContent = `${event.payload.tool ?? "Nexo"}${event.payload.reason ? ` · ${event.payload.reason}` : ""}`;
    detail.append(payload);
    item.append(timestamp, detail);
    auditList.prepend(item);
    while (auditList.children.length > 30) auditList.lastElementChild.remove();
  });
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  voiceState.textContent = "DISPONIBLE";
  const recognition = new SpeechRecognition();
  recognition.lang = "es-ES";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  voiceButton.addEventListener("click", () => {
    try {
      recognition.start();
    } catch {
      showToast("El dictado ya está activo.");
    }
  });
  recognition.addEventListener("start", () => {
    voiceButton.classList.add("listening");
    voiceButton.title = "Escuchando…";
  });
  recognition.addEventListener("end", () => {
    voiceButton.classList.remove("listening");
    voiceButton.title = "Dictar mensaje";
  });
  recognition.addEventListener("result", (event) => {
    message.value = `${message.value}${message.value ? " " : ""}${event.results[0][0].transcript}`;
    message.focus();
  });
  recognition.addEventListener("error", () => showToast("No se pudo completar el dictado."));
} else {
  voiceState.textContent = "NO DISPONIBLE";
  voiceButton.disabled = true;
  voiceButton.title = "El dictado no está disponible en este navegador";
}

function updateClock() {
  const now = new Date();
  document.querySelector("#system-clock").textContent = now.toLocaleTimeString("es-ES", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  document.querySelector("#greeting-time").textContent = now.toLocaleTimeString("es-ES", {
    hour: "2-digit", minute: "2-digit",
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const requestText = message.value.trim();
  if (!requestText) return;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  appendMessage("user", requestText);
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: requestText, data_class: dataClass.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail ?? "No se pudo planificar la solicitud");
    for (const action of result.actions) addAction(action);
    message.value = "";
    if (!result.actions.length) {
      appendMessage("assistant", "No he encontrado una acción que ejecutar para esa solicitud.");
    } else {
      const pending = result.actions.filter((action) => action.status === "pending_approval").length;
      const completed = result.actions.filter((action) => action.status === "succeeded").length;
      const summary = pending
        ? `He preparado ${result.actions.length} acción${result.actions.length === 1 ? "" : "es"}; ${pending} ${pending === 1 ? "espera" : "esperan"} tu aprobación antes de continuar.`
        : `Listo. He procesado ${completed} acción${completed === 1 ? "" : "es"}. Puedes ver los resultados verificados en Actividad de esta sesión.`;
      appendMessage("assistant", summary);
    }
  } catch (error) {
    appendMessage("assistant", `No he podido completar la solicitud: ${error.message}`);
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#refresh-pending").addEventListener("click", loadPending);
upcomingDays.addEventListener("change", loadPending);
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    message.value = button.dataset.prompt;
    message.focus();
  });
});
updateClock();
window.setInterval(updateClock, 1000);
loadPending();
loadPendingActions();
window.setInterval(loadPendingActions, 5000);
connectAudit();