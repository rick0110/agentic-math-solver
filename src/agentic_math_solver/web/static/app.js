const chatWindow = document.getElementById("chat-window");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const healthPill = document.getElementById("health-pill");

let history = [];
let busy = false;

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMessage(role, content, extraClass = "") {
  const bubble = document.createElement("div");
  bubble.className = `message ${role} ${extraClass}`.trim();
  bubble.innerHTML = escapeHtml(content).replaceAll("\n", "<br>");
  chatWindow.appendChild(bubble);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return bubble;
}

function setBusy(value) {
  busy = value;
  sendBtn.disabled = value;
  messageInput.disabled = value;
  sendBtn.textContent = value ? "Enviando..." : "Enviar";
}

function resetChat() {
  history = [];
  chatWindow.innerHTML = "";
  renderMessage("system", "Bem-vindo. Envie um problema para conversar com o solver local.");
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (data.model_ready) {
      healthPill.textContent = "modelo pronto";
      healthPill.className = "pill pill-ok";
    } else {
      healthPill.textContent = "modelo indisponível";
      healthPill.className = "pill pill-warn";
    }
  } catch (error) {
    healthPill.textContent = "backend offline";
    healthPill.className = "pill pill-bad";
  }
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || busy) {
    return;
  }

  renderMessage("user", text);
  history.push({ role: "user", content: text });
  messageInput.value = "";
  setBusy(true);

  const placeholder = renderMessage("assistant", "Pensando...");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history }),
    });
    const data = await response.json();

    placeholder.remove();

    if (!response.ok || !data.ok) {
      const errorText = data.error || "Falha ao consultar o backend local.";
      renderMessage("assistant", errorText, "error");
      history.push({ role: "assistant", content: errorText });
      return;
    }

    const answer = `Resposta: ${data.answer}\nVotos: ${JSON.stringify(data.vote_counts)}\nJuiz usado: ${data.used_judge}\n${data.judge_notes ? `\nNotas do juiz: ${data.judge_notes}` : ""}`;
    renderMessage("assistant", answer);
    history.push({ role: "assistant", content: answer });
  } catch (error) {
    placeholder.remove();
    const errorText = "Erro de rede ao falar com o Flask backend.";
    renderMessage("assistant", errorText, "error");
    history.push({ role: "assistant", content: errorText });
  } finally {
    setBusy(false);
    messageInput.focus();
  }
}

sendBtn.addEventListener("click", sendMessage);
clearBtn.addEventListener("click", () => resetChat());
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

resetChat();
refreshHealth();
setInterval(refreshHealth, 5000);
