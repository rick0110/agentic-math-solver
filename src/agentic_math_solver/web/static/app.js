const chatWindow = document.getElementById("chat-window");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const healthPill = document.getElementById("health-pill");
const historyList = document.getElementById("history-list");
const newChatBtn = document.getElementById("new-chat-btn");
const fileInput = document.getElementById("file-input");
const plusBtn = document.getElementById("plus-btn");
const optionsMenu = document.getElementById("options-menu");
const menuAttachBtn = document.getElementById("menu-attach-btn");
const attachmentsPreview = document.getElementById("attachments-preview");

const CONVERSATIONS_KEY = "ams_conversations";
let conversations = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) || "[]");
let currentConversationId = null;
let busy = false;
let pendingFiles = [];

plusBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    optionsMenu.classList.toggle("hidden");
});

document.addEventListener("click", (e) => {
    if (!optionsMenu.contains(e.target) && !plusBtn.contains(e.target)) {
        optionsMenu.classList.add("hidden");
    }
});

menuAttachBtn.addEventListener("click", () => {
    fileInput.click();
    optionsMenu.classList.add("hidden");
});

fileInput.addEventListener("change", (e) => {
    for (let file of e.target.files) {
        const reader = new FileReader();
        reader.onload = (evt) => {
            pendingFiles.push({ name: file.name, data: evt.target.result });
            renderAttachments();
        };
        reader.readAsDataURL(file);
    }
    fileInput.value = "";
});

function renderAttachments() {
    attachmentsPreview.innerHTML = "";
    pendingFiles.forEach((f, i) => {
        const chip = document.createElement("div");
        chip.className = "attachment-chip";
        chip.innerHTML = `<span>${f.name}</span><span class="remove" onclick="removeFile(${i})">×</span>`;
        attachmentsPreview.appendChild(chip);
    });
}

window.removeFile = function(index) {
    pendingFiles.splice(index, 1);
    renderAttachments();
};

// Auto-resize textarea
messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
    if(this.value === '') {
        this.style.height = 'auto';
    }
});

function saveConversations() {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    renderSidebar();
}

function createNewChat() {
    const id = Date.now().toString();
    const newConv = { id, title: "New Conversation", messages: [] };
    conversations.unshift(newConv);
    currentConversationId = id;
    saveConversations();
    loadConversation(id);
}

function loadConversation(id) {
    currentConversationId = id;
    renderSidebar();
    chatWindow.innerHTML = "";
    
    const conv = conversations.find(c => c.id === id);
    if (!conv) return;

    if (conv.messages.length === 0) {
        renderWelcomeScreen();
    } else {
        conv.messages.forEach(msg => {
            renderBubble(msg.role, msg.content, msg.extraClass);
        });
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
}

function renderWelcomeScreen() {
    chatWindow.innerHTML = `
      <div class="welcome-screen">
        <div class="welcome-logo">Σ</div>
        <div class="welcome-title">Como posso te ajudar com matemática hoje?</div>
        <div class="welcome-suggestions">
          <div class="suggestion-card" onclick="setAndSend('Resolva a equação quadrática: 2x² - 4x - 6 = 0')">
            <h4>Resolver Equações</h4>
            <p>Descubra as raízes passo a passo</p>
          </div>
          <div class="suggestion-card" onclick="setAndSend('Me explique o Teorema de Pitágoras e dê um exemplo prático')">
            <h4>Aprender Conceitos</h4>
            <p>Explicações didáticas de teoria matemática</p>
          </div>
          <div class="suggestion-card" onclick="setAndSend('Crie um fluxograma explicando como fatorar um polinômio usando mermaid')">
            <h4>Visualizar Processos</h4>
            <p>Geração de fluxogramas com Mermaid</p>
          </div>
          <div class="suggestion-card" onclick="setAndSend('Fatore a seguinte expressão: x³ - 3x² + 3x - 1')">
            <h4>Fatoração</h4>
            <p>Redução e simplificação algébrica</p>
          </div>
        </div>
      </div>
    `;
}

window.setAndSend = function(text) {
    const input = document.getElementById("message-input");
    input.value = text;
    input.style.height = 'auto';
    input.style.height = (input.scrollHeight) + 'px';
    sendMessage();
};

function renderSidebar() {
    historyList.innerHTML = "";
    conversations.forEach(conv => {
        const li = document.createElement("li");
        li.className = "history-item";
        if (conv.id === currentConversationId) li.classList.add("active");
        li.textContent = conv.title || "New Conversation";
        li.onclick = () => loadConversation(conv.id);
        historyList.appendChild(li);
    });
}

function formatMarkdown(text) {
    if (window.marked) {
        return marked.parse(text);
    }
    return String(text);
}

function renderBubble(role, content, extraClass = "") {
    const wrapper = document.createElement("div");
    wrapper.className = `message-wrapper ${role} ${extraClass}`.trim();
    
    let avatarChar = role === "user" ? "U" : "Σ";
    let avatarHtml = `<div class="avatar ${role}">${avatarChar}</div>`;
    
    let contentHtml = "";
    if (extraClass === 'thinking') {
        contentHtml = `<div class="spinning-sigma">Σ</div><span style="margin-left:10px;">Calculando e escrevendo a solução...</span>`;
    } else {
        contentHtml = formatMarkdown(content);
    }
    
    wrapper.innerHTML = `
      <div class="message-content">
        ${avatarHtml}
        <div class="message">${contentHtml}</div>
      </div>
    `;
    
    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    
    if (extraClass !== 'thinking') {
        // Highlight code
        if (window.hljs) {
            wrapper.querySelectorAll('pre code').forEach((block) => {
                if (!block.classList.contains('language-mermaid')) {
                    hljs.highlightElement(block);
                }
            });
        }
        
        // Process Mermaid
        if (window.mermaid) {
            const mermaidBlocks = wrapper.querySelectorAll('code.language-mermaid');
            mermaidBlocks.forEach(block => {
                const pre = block.parentElement;
                const div = document.createElement('div');
                div.className = 'mermaid';
                div.textContent = block.textContent;
                if (pre.tagName === 'PRE') {
                    pre.replaceWith(div);
                } else {
                    block.replaceWith(div);
                }
            });
            const mNodes = wrapper.querySelectorAll('.mermaid');
            if (mNodes.length > 0) {
                window.mermaid.run({ nodes: mNodes }).catch(e => console.error('Mermaid err', e));
            }
        }
        
        if (window.MathJax) {
            MathJax.typesetPromise([wrapper]).catch(err => console.log('MathJax error', err));
        }
    }
    
    return wrapper;
}

function setBusy(value) {
  busy = value;
  sendBtn.disabled = value;
  messageInput.disabled = value;
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (data.model_ready) {
      healthPill.textContent = "System Ready";
      healthPill.className = "pill pill-ok";
    } else {
      healthPill.textContent = "Model Offline";
      healthPill.className = "pill pill-warn";
    }
  } catch (error) {
    healthPill.textContent = "Backend Offline";
    healthPill.className = "pill pill-bad";
  }
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || busy) return;

  if (!currentConversationId || !conversations.find(c => c.id === currentConversationId)) {
      createNewChat();
  }

  const conv = conversations.find(c => c.id === currentConversationId);
  
  // Set title to first message if it's "New Conversation"
  if (conv.messages.length === 0) {
      chatWindow.innerHTML = ""; // Remove welcome screen
      conv.title = text.substring(0, 30) + (text.length > 30 ? "..." : "");
      renderSidebar();
  }

  renderBubble("user", text);
  conv.messages.push({ role: "user", content: text });
  saveConversations();

  const filesPayload = [...pendingFiles];
  pendingFiles = [];
  renderAttachments();

  messageInput.value = "";
  messageInput.style.height = 'auto';
  setBusy(true);

  const placeholder = renderBubble("assistant", "", "thinking");

  try {
    const modelInput = document.getElementById("model-input").value;
    const thinkingSelect = document.getElementById("thinking-select").value;
    
    const historyPayload = conv.messages.map(m => ({ role: m.role, content: m.content }));
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
          message: text, 
          history: historyPayload, 
          files: filesPayload,
          options: {
              model: modelInput,
              thinking: thinkingSelect
          }
      }),
    });
    const data = await response.json();

    placeholder.remove();

    if (!response.ok || !data.ok) {
      const errorText = data.error || "Failed to communicate with local backend.";
      renderBubble("assistant", errorText, "error");
      conv.messages.push({ role: "assistant", content: errorText, extraClass: "error" });
      saveConversations();
      return;
    }

    let answer = `**Resposta Final:** ${data.answer}\n\n`;
    if (data.step_by_step) {
        answer += `**Solução Passo a Passo:**\n${data.step_by_step}\n\n`;
    }
    
    renderBubble("assistant", answer);
    conv.messages.push({ role: "assistant", content: answer });
    saveConversations();

  } catch (error) {
    placeholder.remove();
    const errorText = "Network error communicating with the Flask backend.";
    renderBubble("assistant", errorText, "error");
    conv.messages.push({ role: "assistant", content: errorText, extraClass: "error" });
    saveConversations();
  } finally {
    setBusy(false);
    messageInput.focus();
  }
}

sendBtn.addEventListener("click", sendMessage);
newChatBtn.addEventListener("click", createNewChat);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

if (conversations.length === 0) {
    createNewChat();
} else {
    loadConversation(conversations[0].id);
}

refreshHealth();
setInterval(refreshHealth, 5000);
