const chatWindow = document.getElementById("chat-window");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const healthPill = document.getElementById("health-pill");
const historyList = document.getElementById("history-list");
const newChatBtn = document.getElementById("new-chat-btn");
const sidebarSearch = document.getElementById("sidebar-search");
const fileInput = document.getElementById("file-input");
const listFileInput = document.getElementById("list-file-input");
const plusBtn = document.getElementById("plus-btn");
const optionsMenu = document.getElementById("options-menu");
const menuAttachBtn = document.getElementById("menu-attach-btn");
const menuListBtn = document.getElementById("menu-list-btn");
const attachmentsPreview = document.getElementById("attachments-preview");

// Conversations are persisted server-side (one JSON file per conversation
// under outputs/conversations/), so history survives clearing the browser.
// `conversations` only holds lightweight metadata for the sidebar list;
// full message bodies are fetched on demand via loadConversation().
let conversations = [];
let currentConversationId = null;
let currentMessages = [];
let sidebarFilter = "";
let busy = false;
let pendingFiles = [];

const PERSONA_META = {
  formalist: { icon: "\u{1F4D0}", label: "Formalist" },
  architect: { icon: "\u{1F3DB}️", label: "Architect" },
  sentinel: { icon: "\u{1F6E1}️", label: "Sentinel" },
  oracle: { icon: "\u{1F52E}", label: "Oracle" },
  judge: { icon: "⚖️", label: "Judge" },
};

function personaMeta(key) {
  return PERSONA_META[key] || { icon: "\u{1F916}", label: key || "Agent" };
}

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

menuListBtn.addEventListener("click", () => {
    listFileInput.click();
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

listFileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) uploadList(file);
    listFileInput.value = "";
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

async function fetchConversations() {
    try {
        const res = await fetch("/api/conversations");
        const data = await res.json();
        conversations = data.conversations || [];
    } catch (error) {
        conversations = [];
    }
    renderSidebar();
}

function upsertConversationMeta(meta) {
    const idx = conversations.findIndex(c => c.id === meta.id);
    if (idx >= 0) {
        conversations[idx] = { ...conversations[idx], ...meta };
    } else {
        conversations.unshift(meta);
    }
    conversations.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
}

async function persistConversation() {
    if (!currentConversationId) {
        currentConversationId = Date.now().toString();
    }
    const firstUserMsg = currentMessages.find(m => m.role === "user");
    const title = firstUserMsg
        ? firstUserMsg.content.substring(0, 40) + (firstUserMsg.content.length > 40 ? "..." : "")
        : "Nova Conversa";

    try {
        const res = await fetch(`/api/conversations/${currentConversationId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, messages: currentMessages }),
        });
        const data = await res.json();
        if (data.ok) {
            upsertConversationMeta({
                id: currentConversationId,
                title: data.conversation.title,
                updated_at: data.conversation.updated_at,
                created_at: data.conversation.created_at,
                message_count: currentMessages.length,
            });
            renderSidebar();
        }
    } catch (error) {
        // Local session state still holds the messages; a retry on the next
        // turn will attempt to persist again.
    }
}

function createNewChat() {
    currentConversationId = null;
    currentMessages = [];
    chatWindow.innerHTML = "";
    renderWelcomeScreen();
    renderSidebar();
}

async function loadConversation(id) {
    currentConversationId = id;
    renderSidebar();
    chatWindow.innerHTML = "";

    try {
        const res = await fetch(`/api/conversations/${id}`);
        if (!res.ok) {
            renderWelcomeScreen();
            return;
        }
        const data = await res.json();
        currentMessages = (data.conversation && data.conversation.messages) || [];
    } catch (error) {
        currentMessages = [];
    }

    if (currentMessages.length === 0) {
        renderWelcomeScreen();
    } else {
        currentMessages.forEach(msg => {
            renderBubble(msg.role, msg.content, msg.extraClass);
        });
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
}

async function renameConversation(id, newTitle) {
    const title = newTitle.trim();
    if (!title) return;
    try {
        const res = await fetch(`/api/conversations/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
        });
        const data = await res.json();
        if (data.ok) {
            upsertConversationMeta({ id, title: data.conversation.title, updated_at: data.conversation.updated_at });
            renderSidebar();
        }
    } catch (error) {
        // Ignore; sidebar keeps the previous title.
    }
}

async function deleteConversation(id) {
    try {
        await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    } catch (error) {
        // Ignore network errors; still remove locally so the UI stays responsive.
    }
    conversations = conversations.filter(c => c.id !== id);
    if (currentConversationId === id) {
        createNewChat();
    } else {
        renderSidebar();
    }
}

function timeAgo(isoString) {
    if (!isoString) return "";
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return "";
    const diffSeconds = Math.max(0, (Date.now() - then) / 1000);
    if (diffSeconds < 60) return "agora";
    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes}min`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d`;
    return new Date(isoString).toLocaleDateString();
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
          <div class="suggestion-card" onclick="document.getElementById('menu-list-btn').click()">
            <h4>Resolver uma Lista</h4>
            <p>Envie um PDF/imagem com exercícios e receba um PDF resolvido</p>
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

    const filter = sidebarFilter.trim().toLowerCase();
    const visible = filter
        ? conversations.filter(c => (c.title || "").toLowerCase().includes(filter))
        : conversations;

    if (conversations.length === 0) {
        const empty = document.createElement("li");
        empty.className = "history-empty";
        empty.textContent = "Nenhuma conversa ainda";
        historyList.appendChild(empty);
        return;
    }

    if (visible.length === 0) {
        const empty = document.createElement("li");
        empty.className = "history-empty";
        empty.textContent = "Nenhuma conversa encontrada";
        historyList.appendChild(empty);
        return;
    }

    visible.forEach(conv => {
        const li = document.createElement("li");
        li.className = "history-item";
        if (conv.id === currentConversationId) li.classList.add("active");

        const titleEl = document.createElement("span");
        titleEl.className = "history-item-title";
        titleEl.textContent = conv.title || "Nova Conversa";
        titleEl.title = "Duplo clique para renomear";
        titleEl.ondblclick = (e) => {
            e.stopPropagation();
            startRenaming(li, titleEl, conv);
        };

        const timeEl = document.createElement("span");
        timeEl.className = "history-item-time";
        timeEl.textContent = timeAgo(conv.updated_at);

        const actions = document.createElement("span");
        actions.className = "history-item-actions";

        const renameBtn = document.createElement("button");
        renameBtn.className = "history-action-btn";
        renameBtn.title = "Renomear";
        renameBtn.innerHTML = "✏️";
        renameBtn.onclick = (e) => {
            e.stopPropagation();
            startRenaming(li, titleEl, conv);
        };

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "history-action-btn history-action-danger";
        deleteBtn.title = "Excluir";
        deleteBtn.innerHTML = "\u{1F5D1}️";
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            if (confirm(`Excluir a conversa "${conv.title}"? Esta ação não pode ser desfeita.`)) {
                deleteConversation(conv.id);
            }
        };

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        li.appendChild(titleEl);
        li.appendChild(timeEl);
        li.appendChild(actions);
        li.onclick = () => loadConversation(conv.id);
        historyList.appendChild(li);
    });
}

function startRenaming(li, titleEl, conv) {
    const input = document.createElement("input");
    input.className = "history-item-rename-input";
    input.type = "text";
    input.value = conv.title || "";
    titleEl.replaceWith(input);
    input.focus();
    input.select();

    let settled = false;
    const commit = () => {
        if (settled) return;
        settled = true;
        const newTitle = input.value.trim();
        if (newTitle && newTitle !== conv.title) {
            conv.title = newTitle;
            renameConversation(conv.id, newTitle);
        } else {
            renderSidebar();
        }
    };

    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); input.blur(); }
        if (e.key === "Escape") { settled = true; renderSidebar(); }
    });
}

sidebarSearch.addEventListener("input", (e) => {
    sidebarFilter = e.target.value;
    renderSidebar();
});

// Markdown parsers (marked.js) mangle raw LaTeX: underscores become <em>,
// backslashes get treated as escapes, etc. To render math correctly we pull
// out every $...$/$$...$$/\(...\)/\[...\] segment before handing the text to
// marked, then splice the original TeX source back into the resulting HTML
// so MathJax sees it untouched.
const MATH_PATTERNS = [
    /\$\$[\s\S]+?\$\$/g,
    /\\\[[\s\S]+?\\\]/g,
    /\\\([\s\S]+?\\\)/g,
    /\$(?!\$)(?:\\.|[^$\\\n])+?\$/g,
];

function protectMath(text) {
    const store = [];
    let protectedText = String(text);
    MATH_PATTERNS.forEach((pattern) => {
        protectedText = protectedText.replace(pattern, (match) => {
            const token = ` MATH${store.length} `;
            store.push(match);
            return token;
        });
    });
    return { protectedText, store };
}

function restoreMath(html, store) {
    // marked.js may trim/collapse the padding spaces around our token at
    // block boundaries, so tolerate 0-1 whitespace chars on either side.
    return html.replace(/\s?MATH(\d+)\s?/g, (_, i) => store[Number(i)] ?? "");
}

function formatMarkdown(text) {
    if (!window.marked) return String(text);
    const { protectedText, store } = protectMath(text);
    const html = marked.parse(protectedText);
    return restoreMath(html, store);
}

function postProcessRichContent(wrapper) {
    if (window.hljs) {
        wrapper.querySelectorAll('pre code').forEach((block) => {
            if (!block.classList.contains('language-mermaid')) {
                hljs.highlightElement(block);
            }
        });
    }

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

    typesetMathJax(wrapper);
}

// Agent/judge card bodies stream in as plain text (not run through marked),
// but MathJax scans raw text nodes for $...$/\(...\) delimiters directly, so
// this alone is enough to render the LaTeX the model writes mid-reasoning.
function typesetMathJax(...elements) {
    if (!window.MathJax) return;
    MathJax.typesetPromise(elements).catch(err => console.log('MathJax error', err));
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
        postProcessRichContent(wrapper);
    }

    return wrapper;
}

// ---------------------------------------------------------------------------
// Swarm panel: renders live agent cards inside a message bubble as NDJSON
// streaming events arrive (agent_start/agent_token/agent_tool_*/agent_done,
// judge_*, summary_*). Reused both by the main chat and by each question of
// a "solve list" job.
// ---------------------------------------------------------------------------
function createSwarmPanel(gridEl, summaryEl) {
    const cards = {};

    function ensureCard(agentId, persona, isJudge) {
        if (cards[agentId]) return cards[agentId];
        const meta = personaMeta(persona);
        const personaClass = persona ? ` persona-${persona}` : "";
        const card = document.createElement("div");
        card.className = `agent-card status-running${personaClass}${isJudge ? " judge-card" : ""}`;
        card.innerHTML = `
          <div class="agent-card-header">
            <span class="agent-icon">${meta.icon}</span>
            <span class="agent-name">${meta.label}</span>
            <span class="agent-status-dot"></span>
          </div>
          <div class="agent-card-body"></div>
          <div class="agent-card-tool hidden"></div>
          <div class="agent-card-answer hidden"></div>
        `;
        gridEl.appendChild(card);
        cards[agentId] = {
            el: card,
            body: card.querySelector(".agent-card-body"),
            tool: card.querySelector(".agent-card-tool"),
            answer: card.querySelector(".agent-card-answer"),
        };
        return cards[agentId];
    }

    let summaryRaw = "";

    return {
        startAgent(agentId, persona) {
            ensureCard(agentId, persona, false);
        },
        tokenAgent(agentId, delta) {
            const card = ensureCard(agentId, null, false);
            card.body.textContent += delta;
            card.body.scrollTop = card.body.scrollHeight;
        },
        toolAgent(agentId, tool, phase, payload) {
            const card = ensureCard(agentId, null, false);
            card.tool.classList.remove("hidden");
            if (phase === "start") {
                card.tool.textContent = `\u{1F527} Executando ${tool}...`;
            } else {
                const preview = (payload || "").toString().slice(0, 200);
                card.tool.textContent = `✓ ${tool}: ${preview}`;
            }
        },
        doneAgent(agentId, answer) {
            const card = ensureCard(agentId, null, false);
            card.el.classList.remove("status-running");
            card.el.classList.add("status-done");
            if (answer) {
                card.answer.classList.remove("hidden");
                card.answer.textContent = `Resposta: ${answer}`;
            } else {
                card.answer.classList.remove("hidden");
                card.answer.classList.add("agent-card-answer-empty");
                card.answer.textContent = "Sem resposta extraída";
            }
            typesetMathJax(card.body, card.answer);
        },
        startJudge() {
            ensureCard("judge", "judge", true);
        },
        tokenJudge(delta) {
            const card = ensureCard("judge", "judge", true);
            card.body.textContent += delta;
            card.body.scrollTop = card.body.scrollHeight;
        },
        doneJudge(answer) {
            const card = ensureCard("judge", "judge", true);
            card.el.classList.remove("status-running");
            card.el.classList.add("status-done");
            card.answer.classList.remove("hidden");
            card.answer.textContent = answer ? `Decisão: ${answer}` : "Sem decisão";
            typesetMathJax(card.body, card.answer);
        },
        startSummary() {
            summaryEl.classList.add("summary-loading");
            summaryEl.textContent = "";
        },
        tokenSummary(delta) {
            summaryRaw += delta;
            summaryEl.textContent = summaryRaw;
            summaryEl.scrollTop = summaryEl.scrollHeight;
        },
        finalize(markdown) {
            summaryEl.classList.remove("summary-loading");
            summaryEl.innerHTML = formatMarkdown(markdown);
            postProcessRichContent(summaryEl);
        },
        showError(message) {
            summaryEl.classList.remove("summary-loading");
            summaryEl.innerHTML = `<span class="error-text">${message}</span>`;
        },
    };
}

function dispatchSwarmEvent(panel, event) {
    switch (event.type) {
        case "agent_start":
            panel.startAgent(event.agent, event.persona);
            break;
        case "agent_token":
            panel.tokenAgent(event.agent, event.delta);
            break;
        case "agent_tool_start":
            panel.toolAgent(event.agent, event.tool, "start", event.input);
            break;
        case "agent_tool_result":
            panel.toolAgent(event.agent, event.tool, "result", event.output);
            break;
        case "agent_done":
            panel.doneAgent(event.agent, event.answer);
            break;
        case "judge_start":
            panel.startJudge();
            break;
        case "judge_token":
            panel.tokenJudge(event.delta);
            break;
        case "judge_done":
            panel.doneJudge(event.answer);
            break;
        case "summary_start":
            panel.startSummary();
            break;
        case "summary_token":
            panel.tokenSummary(event.delta);
            break;
        default:
            break;
    }
}

function buildFinalMarkdown(finalEvent) {
    let markdown = `**Resposta Final:** ${finalEvent.final_answer}\n\n`;
    if (finalEvent.educational_summary) {
        markdown += `**Solução Passo a Passo:**\n${finalEvent.educational_summary}\n\n`;
    }
    return markdown;
}

async function consumeNdjson(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalEvent = null;

    function handleLine(line) {
        if (!line.trim()) return;
        let event;
        try {
            event = JSON.parse(line);
        } catch (e) {
            return;
        }
        if (event.type === "error") {
            throw new Error(event.message || "Erro no processamento do backend.");
        }
        if (event.type === "final") {
            finalEvent = event;
        }
        onEvent(event);
    }

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) handleLine(line);
    }
    if (buffer.trim()) handleLine(buffer);

    return finalEvent;
}

function createStreamBubble() {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper assistant";
    wrapper.innerHTML = `
      <div class="message-content">
        <div class="avatar assistant">Σ</div>
        <div class="message">
          <div class="swarm-status">\u{1F9E0} Agentes raciocinando ao vivo...</div>
          <div class="swarm-grid"></div>
          <div class="summary-markdown"></div>
        </div>
      </div>
    `;
    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const gridEl = wrapper.querySelector(".swarm-grid");
    const summaryEl = wrapper.querySelector(".summary-markdown");
    const statusEl = wrapper.querySelector(".swarm-status");
    const panel = createSwarmPanel(gridEl, summaryEl);

    return {
        wrapper,
        onEvent(event) {
            if (event.type === "summary_done") statusEl.textContent = "✅ Solução consolidada";
            dispatchSwarmEvent(panel, event);
            chatWindow.scrollTop = chatWindow.scrollHeight;
        },
        finalize(finalEvent) {
            panel.finalize(buildFinalMarkdown(finalEvent));
            chatWindow.scrollTop = chatWindow.scrollHeight;
        },
        showError(message) {
            statusEl.textContent = "⚠️ Erro";
            panel.showError(message);
        },
        remove() {
            wrapper.remove();
        },
    };
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

  if (currentMessages.length === 0) {
      chatWindow.innerHTML = "";
  }

  renderBubble("user", text);
  currentMessages.push({ role: "user", content: text });
  persistConversation();

  const filesPayload = [...pendingFiles];
  pendingFiles = [];
  renderAttachments();

  messageInput.value = "";
  messageInput.style.height = 'auto';
  setBusy(true);

  const stream = createStreamBubble();

  try {
    const modelInput = document.getElementById("model-input").value;
    const thinkingSelect = document.getElementById("thinking-select").value;

    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
          message: text,
          files: filesPayload,
          options: {
              model: modelInput,
              thinking: thinkingSelect
          }
      }),
    });

    if (!response.ok) {
      const errJson = await response.json().catch(() => ({ error: "Falha ao comunicar com o backend." }));
      stream.showError(errJson.error || "Falha ao comunicar com o backend.");
      currentMessages.push({ role: "assistant", content: errJson.error || "Falha ao comunicar com o backend.", extraClass: "error" });
      persistConversation();
      return;
    }

    const finalEvent = await consumeNdjson(response, (event) => stream.onEvent(event));

    if (!finalEvent) {
      stream.showError("O backend encerrou a conexão sem enviar uma resposta final.");
      return;
    }

    stream.finalize(finalEvent);
    const finalMarkdown = buildFinalMarkdown(finalEvent);
    currentMessages.push({ role: "assistant", content: finalMarkdown });
    persistConversation();

  } catch (error) {
    stream.showError(error.message || "Erro de rede comunicando com o backend.");
    currentMessages.push({ role: "assistant", content: error.message || "Erro de rede.", extraClass: "error" });
    persistConversation();
  } finally {
    setBusy(false);
    messageInput.focus();
  }
}

// ---------------------------------------------------------------------------
// "Resolver Lista" flow: upload a problem-set file (PDF/image/text), watch
// each question get solved live (reusing the swarm panel), then download the
// generated PDF.
// ---------------------------------------------------------------------------
function createListJobBubble(filename) {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper assistant list-job";
    wrapper.innerHTML = `
      <div class="message-content">
        <div class="avatar assistant">Σ</div>
        <div class="message">
          <div class="list-job-header">
            <span>\u{1F4C4} Resolvendo lista: <b>${filename}</b></span>
            <span class="list-progress">preparando...</span>
          </div>
          <div class="list-questions"></div>
          <div class="list-download hidden"></div>
        </div>
      </div>
    `;
    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const questionsEl = wrapper.querySelector(".list-questions");
    const progressEl = wrapper.querySelector(".list-progress");
    const downloadEl = wrapper.querySelector(".list-download");

    const questionPanels = {};
    let totalCount = 0;
    let doneCount = 0;

    function ensureQuestion(idx, preview) {
        if (questionPanels[idx]) return questionPanels[idx];
        const block = document.createElement("div");
        block.className = "list-question";
        block.innerHTML = `
          <div class="list-question-header">Questão ${idx}${preview ? " — " + preview : ""}</div>
          <div class="swarm-grid"></div>
          <div class="summary-markdown"></div>
        `;
        questionsEl.appendChild(block);
        const panel = createSwarmPanel(block.querySelector(".swarm-grid"), block.querySelector(".summary-markdown"));
        questionPanels[idx] = panel;
        chatWindow.scrollTop = chatWindow.scrollHeight;
        return panel;
    }

    return {
        handleEvent(event) {
            if (event.type === "list_parsed") {
                totalCount = event.count;
                progressEl.textContent = `0/${totalCount} questões`;
                event.previews.forEach((preview, i) => ensureQuestion(i + 1, preview));
                return null;
            }
            if (event.type === "pdf_ready") {
                downloadEl.classList.remove("hidden");
                downloadEl.innerHTML = `<a class="download-pdf-btn" href="${event.url}" download>⬇️ Baixar PDF Resolvido</a>`;
                progressEl.textContent = `${totalCount}/${totalCount} concluído`;
                chatWindow.scrollTop = chatWindow.scrollHeight;
                return event.url;
            }
            const idx = event.problem_index;
            if (idx === undefined) return null;
            const panel = ensureQuestion(idx);
            dispatchSwarmEvent(panel, event);
            if (event.type === "final") {
                panel.finalize(buildFinalMarkdown(event));
                doneCount += 1;
                progressEl.textContent = `${doneCount}/${totalCount || "?"} questões`;
            }
            chatWindow.scrollTop = chatWindow.scrollHeight;
            return null;
        },
        showError(message) {
            progressEl.textContent = "erro";
            const errBlock = document.createElement("div");
            errBlock.className = "error-text";
            errBlock.textContent = message;
            questionsEl.appendChild(errBlock);
        },
    };
}

async function uploadList(file) {
    const reader = new FileReader();
    reader.onload = async (evt) => {
        const base64 = evt.target.result;

        if (currentMessages.length === 0) {
            chatWindow.innerHTML = "";
        }

        const userMsg = `\u{1F4CE} Lista enviada: **${file.name}**`;
        renderBubble("user", userMsg);
        currentMessages.push({ role: "user", content: userMsg });
        persistConversation();

        setBusy(true);
        const job = createListJobBubble(file.name);

        try {
            const modelInput = document.getElementById("model-input").value;
            const thinkingSelect = document.getElementById("thinking-select").value;

            const response = await fetch("/api/list/upload", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    file: { name: file.name, data: base64 },
                    options: { model: modelInput, thinking: thinkingSelect },
                }),
            });

            if (!response.ok) {
                const errJson = await response.json().catch(() => ({ error: "Falha ao processar a lista." }));
                job.showError(errJson.error || "Falha ao processar a lista.");
                return;
            }

            let pdfUrl = null;
            await consumeNdjson(response, (event) => {
                const result = job.handleEvent(event);
                if (result) pdfUrl = result;
            });

            const summaryMsg = pdfUrl
                ? `✅ Lista **${file.name}** resolvida! [Baixar PDF resolvido](${pdfUrl})`
                : `Lista **${file.name}** processada, mas nenhum PDF foi gerado.`;
            currentMessages.push({ role: "assistant", content: summaryMsg });
            persistConversation();
        } catch (error) {
            job.showError(error.message || "Erro de rede ao processar a lista.");
        } finally {
            setBusy(false);
        }
    };
    reader.readAsDataURL(file);
}

sendBtn.addEventListener("click", sendMessage);
newChatBtn.addEventListener("click", createNewChat);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

(async function bootstrap() {
    await fetchConversations();
    if (conversations.length === 0) {
        createNewChat();
    } else {
        loadConversation(conversations[0].id);
    }
})();

refreshHealth();
setInterval(refreshHealth, 5000);
