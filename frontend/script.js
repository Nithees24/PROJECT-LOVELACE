const pageShell = document.getElementById("pageShell");
const leftPanelToggle = document.getElementById("leftPanelToggle");
const chatWindow = document.getElementById("chatWindow");
const chatStage = document.getElementById("chatStage");
const chatIntro = document.getElementById("chatIntro");
const modeChipInline = document.getElementById("modeChipInline");
const modeChipClose = document.getElementById("modeChipClose");
const composer = document.getElementById("composer");
const promptInput = document.getElementById("promptInput");
const themeToggleCheckbox = document.getElementById("themeToggleCheckbox");
const sendButton = composer.querySelector(".send-button");
const stopButton = document.getElementById("stopButton");
const deepResearchToggle = document.getElementById("deepResearchToggle");
const artifactToggle = document.getElementById("artifactToggle");
const documentToggle = document.getElementById("documentToggle");
const modeChipLabel = document.getElementById("modeChipLabel");
const accountPopover = document.getElementById("accountPopover");
const attachmentTrigger = document.getElementById("attachmentTrigger");
const attachmentMenu = document.getElementById("attachmentMenu");
const uploadDocBtn = document.getElementById("uploadDocBtn");
const docInput = document.getElementById("docInput");
const composerAttachments = document.getElementById("composerAttachments");
const profileMenuButton = document.getElementById("profileMenuButton");
const profileMenu = document.getElementById("profileMenu");
const historyItems = Array.from(document.querySelectorAll(".history-topic"));
const historyMoreButtons = Array.from(document.querySelectorAll(".history-more"));
const confirmOverlay = document.getElementById("confirmOverlay");
const confirmTitle = document.getElementById("confirmTitle");
const confirmDescription = document.getElementById("confirmDescription");
const confirmBtn = document.getElementById("confirmBtn");
const confirmCancelBtn = document.getElementById("confirmCancelBtn");

const promptOverlay = document.getElementById("promptOverlay");
const promptTitle = document.getElementById("promptTitle");
const promptInputBox = document.getElementById("promptInputBox");
const promptCancelBtn = document.getElementById("promptCancelBtn");
const promptBtn = document.getElementById("promptBtn");

const CHAT_MODE = "Chat Agent";
const DEEP_MODE = "Deep Research";
// Artifact mode runs the normal chat agent but instructs it to return a
// self-contained deliverable. The user can also just ask for one in plain
// language — this only makes the intent explicit and removes the guesswork.
const ARTIFACT_MODE = "Artifact";
// Document mode runs its own agent: an interview (format, then whatever the
// request leaves open) followed by web research and a written document.
const DOC_MODE = "Document";
const API_ENDPOINT = (window.LOVELACE_CONFIG && window.LOVELACE_CONFIG.API_ENDPOINT) || "http://127.0.0.1:8000/api/chat";
const BASE_URL = API_ENDPOINT.replace("/api/chat", "");
const CONV_API = `${BASE_URL}/api/conversations`;
const MSG_API = `${BASE_URL}/api/messages`;

// The app is only functional when SERVED by the backend over HTTP. When the
// .html file is opened directly from disk (file://), run in a static PREVIEW
// mode: render the default UI but make no backend calls and no auth redirects,
// so the shell is viewable even with the server off. The working app lives at
// http://localhost:8000.
const IS_SERVED = location.protocol === "http:" || location.protocol === "https:";

// Check if user is logged in
const userId = localStorage.getItem("lovelace_user_id");
const userName = localStorage.getItem("lovelace_user_name");
const authToken = localStorage.getItem("lovelace_token");

if (IS_SERVED && (!userId || !authToken)) {
  window.location.replace("login.html");
}

// Clear credentials and bounce to login (used on 401 and sign-out)
const clearSessionAndRedirect = () => {
  localStorage.removeItem("lovelace_user_id");
  localStorage.removeItem("lovelace_user_name");
  localStorage.removeItem("lovelace_token");
  window.location.replace("login.html");
};

// All API calls go through this: attaches the bearer token (SEC-01) and
// bounces to login if the server rejects the session (401).
const authFetch = (url, options = {}) => {
  const headers = { ...(options.headers || {}) };
  const token = localStorage.getItem("lovelace_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return window.fetch(url, { ...options, headers }).then((res) => {
    if (res.status === 401) {
      clearSessionAndRedirect();
      throw new Error("Session expired");
    }
    return res;
  });
};

const userNameElements = Array.from(document.querySelectorAll("[data-user-name]"));
const userAvatarElements = Array.from(document.querySelectorAll("[data-user-avatar]"));

const getInitials = (name) => {
  const safeName = (name || "").trim();
  if (!safeName) {
    return "AK";
  }

  const parts = safeName.split(/\s+/).filter(Boolean);
  if (parts.length > 1) {
    return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
  }

  return safeName.slice(0, 2).toUpperCase();
};

const updateUserIdentity = (name) => {
  const displayName = (name || "").trim() || "Research Lead";
  const initials = getInitials(displayName);

  userNameElements.forEach((element) => {
    element.textContent = displayName;
  });

  userAvatarElements.forEach((element) => {
    element.textContent = initials;
  });
};

updateUserIdentity(userName);

// Sign out logic
const signOutButton = document.getElementById("signOutBtn");
if (signOutButton) {
  signOutButton.addEventListener("click", () => {
    closeAccountMenu();
    clearSessionAndRedirect();
  });
}

let activeMode = CHAT_MODE;
let isSending = false;
let activeAbortController = null;
let activeSessionId = null;
const LOVELACE_LOGO_SVG = `
  <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">
    <circle cx="32" cy="32" r="6" class="logo-core"></circle>
    <ellipse cx="32" cy="32" rx="22" ry="10" class="logo-orbit"></ellipse>
    <ellipse cx="32" cy="32" rx="22" ry="10" class="logo-orbit" transform="rotate(60 32 32)"></ellipse>
    <ellipse cx="32" cy="32" rx="22" ry="10" class="logo-orbit" transform="rotate(120 32 32)"></ellipse>
    <circle cx="52" cy="32" r="3" class="logo-node"></circle>
    <circle cx="22" cy="15" r="3" class="logo-node"></circle>
    <circle cx="23" cy="49" r="3" class="logo-node"></circle>
  </svg>
`;

const createPanelIcon = (collapsed) => {
  return collapsed
    ? `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2"></rect>
        <path d="M9 5v14"></path>
        <path d="M5 12h2"></path>
      </svg>
    `
    : `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2"></rect>
        <path d="M9 5v14"></path>
        <path d="M7 12H5"></path>
      </svg>
    `;
};

const autoResize = () => {
  promptInput.style.height = "auto";
  promptInput.style.height = `${promptInput.scrollHeight}px`;
};

const initLoadAnimations = () => {
  const brandMark = document.getElementById("brandMark");
  const revealTargets = [
    ...document.querySelectorAll(".page-topbar > *"),
    ...document.querySelectorAll(".sidebar .panel-body > *"),
    ...document.querySelectorAll(".chat-stage > .chat-intro, .chat-stage > .chat-window, .chat-stage > .composer, .chat-stage > .composer-note")
  ];

  revealTargets.forEach((element, index) => {
    element.classList.add("reveal-on-load");
    element.style.setProperty("--reveal-order", index);
  });

  window.requestAnimationFrame(() => {
    document.body.classList.add("is-loaded");
  });

  // Stop the logo loading animation after the page settle delay
  if (brandMark) {
    window.setTimeout(() => {
      brandMark.classList.remove("is-loading");
    }, 1800);
  }
};

const createMessage = (role, content, options = {}) => {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.classList.add("animate-in");
  if (options.pending) {
    article.classList.add("is-pending");
  }
  if (options.error) {
    article.classList.add("is-error");
  }

  const card = document.createElement("div");
  card.className = "message-card";

  const body = document.createElement("div");
  body.className = "message-text";

  // Check if it's a file message
  if (content && content.startsWith("Uploaded file: ")) {
    const fileName = content.replace("Uploaded file: ", "");
    const isPending = options.fileStatus === "pending";
    const statusText = isPending ? "Indexing document..." : "Document indexed";
    const statusIcon = isPending 
      ? `<div class="spinner-mini" style="width: 16px; height: 16px; border-width: 2px;"></div>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;

    body.innerHTML = `<div class="file-attachment-card ${isPending ? 'is-uploading' : ''}">
        <div class="file-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
        </div>
        <div class="file-info">
          <span class="file-name">${escapeHtml(fileName)}</span>
          <span class="file-meta">${statusText}</span>
        </div>
        <div class="file-status-icon">
          ${statusIcon}
        </div>
      </div>`;
  } else if (role === "assistant") {
    body.innerHTML = parseMarkdown(content || "");
  } else {
    body.textContent = content;
  }

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = LOVELACE_LOGO_SVG;
    article.append(avatar);
  }

  card.append(body);

  // An artifact rides along with the prose as a card that opens the canvas —
  // the deliverable itself lives there, not in the bubble.
  if (role === "assistant" && options.artifact) {
    card.append(buildArtifactCard(options.artifact));
  }

  article.append(card);

  if (role === "assistant" && !options.pending && !options.error) {
    appendAssistantFooter(article, content, options.sources || [], options.model || "");
  }
  const isFileMsg = content && content.startsWith("Uploaded file: ");
  if (role === "user" && !isFileMsg) {
    appendUserFooter(article);
  }

  return article;
};

const appendUserFooter = (article) => {
  const card = article.querySelector(".message-card");
  if (!card || article.querySelector(".message-footer")) return;

  const footer = document.createElement("div");
  footer.className = "message-footer";
  footer.innerHTML = `
    <div class="message-actions-row">
      <button class="msg-action-btn has-tooltip" data-tooltip="Copy prompt" data-action="copy">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
      </button>
      <button class="msg-action-btn has-tooltip" data-tooltip="Edit prompt" data-action="edit">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
      </button>
    </div>
  `;

  footer.querySelectorAll(".msg-action-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === "copy") {
        const text = card.querySelector(".message-text").innerText;
        navigator.clipboard.writeText(text).then(() => {
          btn.classList.add("success");
          setTimeout(() => btn.classList.remove("success"), 1500);
        });
      } else if (action === "edit") {
        enterEditMode(article);
      }
    });
  });

  article.append(footer);
};

const enterEditMode = (article) => {
  const card = article.querySelector(".message-card");
  const textElement = card.querySelector(".message-text");
  const footer = article.querySelector(".message-footer");
  const originalText = textElement.innerText;

  // Hide original content
  textElement.style.display = "none";
  footer.style.display = "none";
  card.classList.add("is-editing");

  const editContainer = document.createElement("div");
  editContainer.className = "edit-container";
  editContainer.innerHTML = `
    <textarea class="edit-textarea">${escapeHtml(originalText)}</textarea>
    <div class="edit-actions">
      <button class="edit-btn cancel" id="editCancel">Cancel</button>
      <button class="edit-btn update" id="editUpdate" disabled>Update</button>
    </div>
  `;

  card.appendChild(editContainer);
  const textarea = editContainer.querySelector(".edit-textarea");
  const updateBtn = editContainer.querySelector("#editUpdate");
  const cancelBtn = editContainer.querySelector("#editCancel");

  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  // Auto-resize textarea
  const resize = () => {
    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + "px";
  };
  textarea.addEventListener("input", () => {
    resize();
    updateBtn.disabled = textarea.value.trim() === originalText.trim() || textarea.value.trim() === "";
  });
  resize();

  cancelBtn.onclick = () => {
    editContainer.remove();
    card.classList.remove("is-editing");
    textElement.style.display = "block";
    footer.style.display = "flex";
  };

  updateBtn.onclick = async () => {
    const newText = textarea.value.trim();
    editContainer.remove();
    card.classList.remove("is-editing");
    textElement.innerText = newText;
    textElement.style.display = "block";
    footer.style.display = "flex";

    // Trigger regeneration
    handlePromptUpdate(article, newText);
  };
};

const handlePromptUpdate = async (userArticle, newText) => {
  // Find the assistant message following this user message
  let nextMsg = userArticle.nextElementSibling;
  while (nextMsg && !nextMsg.classList.contains("message")) {
    nextMsg = nextMsg.nextElementSibling;
  }

  // If the next message is an assistant message, remove it
  if (nextMsg && nextMsg.classList.contains("assistant")) {
    nextMsg.remove();
  }

  // Abort any current generation if needed
  if (activeAbortController) {
    activeAbortController.abort();
  }

  // Create new pending message
  const pendingMessage = createMessage("assistant", "", { pending: true });
  userArticle.after(pendingMessage);

  activeAbortController = new AbortController();

  try {
    const payload = await requestAssistantReply(newText, activeSessionId, { signal: activeAbortController.signal });
    const reply = payload.reply;
    const sources = payload.sources || [];
    const model = payload.model || "";
    pendingMessage.classList.remove("is-pending");
    await typeWriterEffect(pendingMessage.querySelector(".message-text"), reply);
    appendAssistantFooter(pendingMessage, reply, sources, model);
    scrollToBottom();
  } catch (error) {
    pendingMessage.classList.remove("is-pending");
    if (error.name !== 'AbortError') {
      pendingMessage.classList.add("is-error");
      pendingMessage.querySelector(".message-text").textContent = error.message || "Regeneration failed.";
    }
  }
};

const appendAssistantFooter = (article, content, sources = [], model = "") => {
  const card = article.querySelector(".message-card");
  if (!card || card.querySelector(".message-footer")) return;

  const footer = document.createElement("div");
  footer.className = "message-footer";
  let sourcesHtml = "";
  if (sources && sources.length > 0) {
    // Sources are third-party data (scraped pages / search results), never
    // trust url/title as HTML — the dropdown list is left empty here and
    // built with DOM APIs below (SEC-06), not string-concatenated markup.
    sourcesHtml = `
      <div class="msg-sources-container">
        <button class="msg-action-btn sources-btn" data-action="sources" type="button" style="width: auto; padding: 0 12px; display: flex; align-items: center; gap: 6px;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
          <span style="font-size: 0.75rem; font-weight: 600;">Sources</span>
        </button>
        <div class="msg-sources-dropdown" hidden>
          <div class="sources-dropdown-header">Internet Sources</div>
          <div class="sources-dropdown-list"></div>
        </div>
      </div>
    `;
  }

  const displayModel = model || "Lovelace AI";

  footer.innerHTML = `
    <div class="message-actions-row" style="display:flex; justify-content:space-between; width:100%; align-items:center;">
      <div class="msg-actions-left" style="display:flex; gap:6px;">
        <button class="msg-action-btn has-tooltip" data-tooltip="Like response" data-action="like">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>
        </button>
        <button class="msg-action-btn has-tooltip" data-tooltip="Dislike response" data-action="dislike">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path></svg>
        </button>
        <button class="msg-action-btn has-tooltip" data-tooltip="Copy response" data-action="copy">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        </button>
        <button class="msg-action-btn has-tooltip" data-tooltip="Redo response" data-action="redo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
        </button>
        <div class="msg-more-container">
          <button class="msg-action-btn" data-action="more">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
          </button>
          <div class="msg-more-dropdown" hidden>
            <p class="model-info">Generated by Lovelace Intelligence (${escapeHtml(displayModel)})</p>
          </div>
        </div>
      </div>
      ${sourcesHtml}
    </div>
  `;

  // Populate the sources dropdown with real DOM nodes rather than
  // string-concatenated HTML — url/title/hostname are untrusted third-party
  // data (scraped pages, search results) and must never be parsed as markup
  // (SEC-06). Only http/https URLs get a clickable href.
  if (sources && sources.length > 0) {
    const listEl = footer.querySelector(".sources-dropdown-list");
    sources.forEach(s => {
      let hostname = s.url || "";
      let safeHref = null;
      try {
        const parsed = new URL(s.url);
        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
          safeHref = parsed.href;
        }
        hostname = parsed.hostname;
      } catch (e) {
        // Leave hostname as the raw string and safeHref unset (no link).
      }

      const link = document.createElement("a");
      link.className = "source-item-link";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = s.title || "";
      if (safeHref) link.href = safeHref;

      const icon = document.createElement("div");
      icon.className = "source-item-icon";
      icon.style.cssText = "background: rgba(24, 35, 33, 0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.03);";
      const favicon = document.createElement("img");
      favicon.alt = "";
      favicon.style.cssText = "width: 14px; height: 14px; border-radius: 2px;";
      favicon.src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(hostname)}&sz=32`;
      icon.append(favicon);

      const textWrap = document.createElement("div");
      textWrap.className = "source-item-text";
      const titleSpan = document.createElement("span");
      titleSpan.className = "source-item-title";
      titleSpan.textContent = s.title || "Source";
      const urlSpan = document.createElement("span");
      urlSpan.className = "source-item-url";
      urlSpan.textContent = hostname;
      textWrap.append(titleSpan, urlSpan);

      link.append(icon, textWrap);
      listEl.append(link);
    });
  }

  // Action Logic
  footer.querySelectorAll(".msg-action-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === "copy") {
        // Copy entire conversation logic
        const messages = Array.from(chatWindow.querySelectorAll(".message:not(.is-pending)"));
        const conversationText = messages.map(m => {
          const isUser = m.classList.contains("user");
          const role = isUser ? "USER" : "LOVELACE";
          const textElement = m.querySelector(".message-text");
          const text = textElement ? textElement.innerText : "";
          return `${role}:\n${text}`;
        }).join("\n\n---\n\n");

        navigator.clipboard.writeText(conversationText).then(() => {
          btn.classList.add("success");
          setTimeout(() => btn.classList.remove("success"), 1500);
        });
      } else if (action === "like" || action === "dislike") {
        const score = action === "like" ? 1 : -1;
        const isDeselecting = btn.classList.contains("active");

        // If already active, clicking again effectively "undoes" the vote (0)
        // But the user specifically asked for +1 and -1.
        // I'll implement it so clicking toggles the state and notifies the backend.

        btn.classList.toggle("active");
        const otherAction = action === "like" ? "dislike" : "like";
        footer.querySelector(`[data-action="${otherAction}"]`).classList.remove("active");

        if (activeSessionId) {
          authFetch(`${CONV_API}/${activeSessionId}/rate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ score: score })
          }).catch(err => console.error("Rating failed:", err));
        }
      } else if (action === "redo") {
        const messages = Array.from(chatWindow.querySelectorAll(".message.user"));
        if (messages.length > 0) {
          const lastUserMsg = messages[messages.length - 1];
          promptInput.value = lastUserMsg.querySelector(".message-text").textContent;
          composer.requestSubmit();
        }
      } else if (action === "more") {
        const dropdown = btn.nextElementSibling;
        dropdown.hidden = !dropdown.hidden;
      } else if (action === "sources") {
        const dropdown = btn.nextElementSibling;
        dropdown.hidden = !dropdown.hidden;
      }
    });
  });

  card.append(footer);
};

const setComposerBusy = (busy) => {
  isSending = busy;
  promptInput.disabled = busy;
  sendButton.disabled = busy;
  composer.classList.toggle("is-busy", busy);
};

const requestAssistantReply = async (message, sessionId, options = {}) => {
  const response = await authFetch(API_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message,
      mode: activeMode,
      conversation_id: sessionId
    }),
    signal: options.signal
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.error === "string" ? payload.error : "The backend did not return a valid response.";
    throw new Error(detail);
  }

  // The turn was a document request, so there is no chat reply to validate —
  // the caller hands off to the document workspace instead.
  if (payload.route === "document" && payload.brief) {
    return payload;
  }

  if (typeof payload.reply !== "string" || !payload.reply.trim()) {
    throw new Error("The backend returned an empty reply.");
  }

  return payload;
};

const updatePromptPlaceholder = () => {
  promptInput.placeholder =
    activeMode === DEEP_MODE ? "Use Lovelace to deep research"
    : activeMode === ARTIFACT_MODE ? "Describe the app, tool, or file to build"
    : activeMode === DOC_MODE ? "Describe the document you want"
    : "Ask Lovelace";
};

const syncStageState = () => {
  const hasMessages = chatWindow.querySelector(".message") !== null;
  const showChip = activeMode !== CHAT_MODE;

  if (showChip && modeChipLabel) {
    modeChipLabel.textContent =
      activeMode === DEEP_MODE ? "Deep research"
      : activeMode === DOC_MODE ? "Create document"
      : "Create artifact";
  }
  modeChipInline.hidden = !showChip;
  chatWindow.classList.toggle("is-empty", !hasMessages);
  chatIntro.hidden = false;
  chatStage.classList.toggle("is-empty-state", !hasMessages);

  // Reset the scroll button when there are no messages
  if (!hasMessages) {
    scrollToBottomBtn.classList.remove("is-visible");
  }
};

const updateAgentUI = () => {
  // Reflect the active mode on its + menu item. The two are mutually
  // exclusive — selecting one clears the other via setActiveMode.
  if (deepResearchToggle) {
    const on = activeMode === DEEP_MODE;
    deepResearchToggle.classList.toggle("is-active", on);
    deepResearchToggle.setAttribute("aria-pressed", String(on));
  }
  if (artifactToggle) {
    const on = activeMode === ARTIFACT_MODE;
    artifactToggle.classList.toggle("is-active", on);
    artifactToggle.setAttribute("aria-pressed", String(on));
  }
  if (documentToggle) {
    const on = activeMode === DOC_MODE;
    documentToggle.classList.toggle("is-active", on);
    documentToggle.setAttribute("aria-pressed", String(on));
  }
  // Reset composer attachments
  if (composerAttachments) {
    composerAttachments.innerHTML = "";
    composerAttachments.hidden = true;
  }
};

const setActiveMode = (mode) => {
  activeMode = mode;
  updatePromptPlaceholder();
  updateAgentUI();
  // Reflect the mode change in the stage immediately so the Deep Research chip
  // appears/disappears on toggle — otherwise switching back to Chat leaves the
  // chip visible and the mode looks stuck on.
  syncStageState();
  closeAgentMenu();
};

// ══════════════════════════════════════════════════════════════════════
// Deep Research workspace (Phase 2)
// While running: a two-column card of rounded sections — Plan (left,
// editable/approvable) | Steps + Sources (right, live NDJSON event feed).
// When finished it collapses to the report card + summary tabs (see
// presentReport). Consumes the Phase 1 backend contract: POST
// /api/research/plan then POST /api/research/stream.
// ══════════════════════════════════════════════════════════════════════
const RW_ICON_OK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
const RW_ICON_FAIL = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

const rwHostname = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url || ""; }
};
const rwSafeHref = (url) => {
  try { const u = new URL(url); return (u.protocol === "http:" || u.protocol === "https:") ? u.href : ""; }
  catch { return ""; }
};

function buildResearchWorkspace(query) {
  const article = document.createElement("article");
  article.className = "message assistant research-msg animate-in";

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.innerHTML = LOVELACE_LOGO_SVG;
  article.append(avatar);

  const card = document.createElement("div");
  card.className = "message-card research-card";
  card.innerHTML = `
    <div class="rw" data-state="planning">
      <div class="rw-head">
        <div class="rw-head-title">
          <span class="rw-badge">Deep Research</span>
          <span class="rw-query"></span>
        </div>
        <div class="rw-status"><span class="rw-status-dot"></span><span class="rw-status-text">Planning…</span></div>
      </div>
      <div class="rw-preview" hidden></div>
      <div class="rw-body">
        <section class="rw-pane rw-plan-pane">
          <header class="rw-pane-head">Plan</header>
          <div class="rw-plan-scroll"><div class="rw-empty">Building a research plan…</div></div>
          <div class="rw-plan-actions" hidden>
            <button class="rw-approve" type="button" disabled>Start research</button>
            <button class="rw-add-section" type="button">+ Add section</button>
          </div>
        </section>
        <section class="rw-pane rw-activity-pane">
          <div class="rw-asec rw-asec-steps">
            <div class="rw-asec-head">Steps</div>
            <div class="rw-current" hidden><span class="rw-spinner"></span><span class="rw-current-text"></span></div>
            <div class="rw-feed"><div class="rw-empty">Waiting for the plan…</div></div>
          </div>
          <div class="rw-asec rw-sources" hidden>
            <div class="rw-asec-head">Sources <span class="rw-asec-count rw-sources-count">0</span></div>
            <div class="rw-sources-list"></div>
          </div>
        </section>
      </div>
    </div>`;
  article.append(card);
  card.querySelector(".rw-query").textContent = query;

  const root = card.querySelector(".rw");
  const refs = {
    article, card, root,
    statusText: root.querySelector(".rw-status-text"),
    preview: root.querySelector(".rw-preview"),
    body: root.querySelector(".rw-body"),
    planScroll: root.querySelector(".rw-plan-scroll"),
    planActions: root.querySelector(".rw-plan-actions"),
    approveBtn: root.querySelector(".rw-approve"),
    addSectionBtn: root.querySelector(".rw-add-section"),
    current: root.querySelector(".rw-current"),
    currentText: root.querySelector(".rw-current-text"),
    feed: root.querySelector(".rw-feed"),
    sourcesBox: root.querySelector(".rw-sources"),
    sourcesList: root.querySelector(".rw-sources-list"),
    sourcesCount: root.querySelector(".rw-sources-count"),
    _sourceUrls: new Set(),
    _sources: [],
    _feedHasRows: false,
    _secWrap: null,
    _report: null,
    _reportCard: null,
    // Captured while the run streams, replayed into the finished-state summary.
    _steps: [],
    _plan: null,
    _stats: null,
    _metaEl: null,
  };
  refs.setState = (s) => { root.dataset.state = s; };
  refs.setStatus = (t) => { refs.statusText.textContent = t; };
  return { article, refs };
}

function rwMakeQueryRow(value, editable) {
  const row = document.createElement("div");
  row.className = "rw-query-row";
  const inp = document.createElement("input");
  inp.className = "rw-q-input";
  inp.value = value || "";
  inp.placeholder = "search query";
  inp.readOnly = !editable;
  row.append(inp);
  if (editable) {
    const del = document.createElement("button");
    del.className = "rw-mini";
    del.type = "button";
    del.textContent = "✕";
    del.title = "Remove query";
    del.addEventListener("click", () => row.remove());
    row.append(del);
  }
  return row;
}

function rwRenumber(refs) {
  refs._secWrap.querySelectorAll(".rw-sec").forEach((el, i) => {
    el.querySelector(".rw-sec-num").textContent = `Section ${i + 1}`;
  });
}

function rwBuildSectionEl(sec, editable, refs) {
  const el = document.createElement("div");
  el.className = "rw-sec";
  el.innerHTML = `
    <div class="rw-sec-num"></div>
    <button class="rw-mini rw-sec-del" type="button" title="Remove section" hidden>✕</button>
    <input class="rw-sec-title" placeholder="Section title">
    <textarea class="rw-sec-q" rows="2" placeholder="Sub-question"></textarea>
    <div class="rw-queries"></div>
    <button class="rw-mini rw-add-query" type="button" hidden>+ query</button>`;
  el.querySelector(".rw-sec-title").value = sec.title || "";
  el.querySelector(".rw-sec-q").value = sec.question || "";
  const qwrap = el.querySelector(".rw-queries");
  (sec.queries || []).forEach((q) => qwrap.append(rwMakeQueryRow(q, editable)));
  if (editable) {
    const del = el.querySelector(".rw-sec-del");
    del.hidden = false;
    del.addEventListener("click", () => { el.remove(); rwRenumber(refs); });
    const addQ = el.querySelector(".rw-add-query");
    addQ.hidden = false;
    addQ.addEventListener("click", () => qwrap.append(rwMakeQueryRow("", true)));
  } else {
    el.querySelectorAll("input,textarea").forEach((n) => (n.readOnly = true));
  }
  return el;
}

function renderPlanEditor(refs, plan, editable) {
  refs._plan = plan;
  const scroll = refs.planScroll;
  scroll.innerHTML = "";
  const titleEl = document.createElement("input");
  titleEl.className = "rw-plan-title";
  titleEl.value = plan.title || "Research plan";
  titleEl.readOnly = !editable;
  scroll.append(titleEl);
  const secWrap = document.createElement("div");
  secWrap.className = "rw-secwrap";
  secWrap.style.cssText = "display:flex;flex-direction:column;gap:10px;margin-top:8px;";
  scroll.append(secWrap);
  refs._secWrap = secWrap;
  (plan.sections || []).forEach((sec) => secWrap.append(rwBuildSectionEl(sec, editable, refs)));
  rwRenumber(refs);
}

function rwCollectPlan(refs) {
  const titleInput = refs.planScroll.querySelector(".rw-plan-title");
  const title = (titleInput ? titleInput.value : "Research plan").trim() || "Research plan";
  const sections = [];
  refs._secWrap.querySelectorAll(".rw-sec").forEach((el, i) => {
    const t = el.querySelector(".rw-sec-title").value.trim();
    const q = el.querySelector(".rw-sec-q").value.trim();
    const queries = [];
    el.querySelectorAll(".rw-q-input").forEach((inp) => {
      const v = inp.value.trim();
      if (v) queries.push(v);
    });
    if (!t && !q && !queries.length) return;
    sections.push({
      id: `s${i + 1}`,
      title: t || q.slice(0, 60),
      question: q || t,
      queries: queries.length ? queries : [q || t],
    });
  });
  return { title, sections };
}

function renderPlanForApproval(refs, plan) {
  renderPlanEditor(refs, plan, true);
  refs.planActions.hidden = false;
  refs.approveBtn.disabled = false;
  refs.addSectionBtn.onclick = () => {
    refs._secWrap.append(rwBuildSectionEl({ title: "", question: "", queries: [""] }, true, refs));
    rwRenumber(refs);
  };
  refs.feed.innerHTML = `<div class="rw-empty">Review or edit the plan, then approve to begin.</div>`;
  return new Promise((resolve) => {
    refs.approveBtn.onclick = () => {
      const edited = rwCollectPlan(refs);
      if (!edited.sections.length) return;
      refs.approveBtn.disabled = true;
      resolve(edited);
    };
  });
}

// Compact staged preview of the plan (shown before any editing): title,
// what-will-happen timeline, and Edit plan / Start research actions.
function renderPlanPreview(refs, plan) {
  const ICON_SEARCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M3.6 9h16.8M3.6 15h16.8"></path><path d="M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"></path></svg>`;
  const ICON_ANALYZE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="6" x2="20" y2="6"></line><line x1="4" y1="12" x2="14" y2="12"></line><line x1="4" y1="18" x2="17" y2="18"></line></svg>`;
  const ICON_REPORT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>`;
  const ICON_CLOCK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><polyline points="12 7 12 12 15.5 14"></polyline></svg>`;

  refs.preview.innerHTML = `
    <p class="rw-preview-intro">Here's the research plan. Start it as-is, or edit it first.</p>
    <h3 class="rw-preview-title"></h3>
    <div class="rw-pstages">
      <div class="rw-pstage">
        <span class="rw-pstage-ic">${ICON_SEARCH}</span>
        <div class="rw-pstage-body">
          <div class="rw-pstage-name">Research websites</div>
          <ol class="rw-pstage-steps"></ol>
          <button class="rw-more" type="button" hidden>More</button>
        </div>
      </div>
      <div class="rw-pstage">
        <span class="rw-pstage-ic">${ICON_ANALYZE}</span>
        <div class="rw-pstage-body">
          <div class="rw-pstage-name">Analyze results</div>
          <div class="rw-pstage-sub">Cross-check the findings and fill coverage gaps</div>
        </div>
      </div>
      <div class="rw-pstage">
        <span class="rw-pstage-ic">${ICON_REPORT}</span>
        <div class="rw-pstage-body">
          <div class="rw-pstage-name">Create report</div>
          <div class="rw-pstage-sub">Synthesize a cited overview of everything found</div>
        </div>
      </div>
      <div class="rw-pstage">
        <span class="rw-pstage-ic">${ICON_CLOCK}</span>
        <div class="rw-pstage-body"><div class="rw-pstage-name rw-pstage-eta">Ready in a few minutes</div></div>
      </div>
    </div>
    <div class="rw-preview-actions">
      <button class="rw-edit-plan" type="button">Edit plan</button>
      <button class="rw-start" type="button">Start research</button>
    </div>`;

  refs.preview.querySelector(".rw-preview-title").textContent = plan.title || "Research plan";

  const VISIBLE_STEPS = 3;
  const list = refs.preview.querySelector(".rw-pstage-steps");
  const sections = plan.sections || [];
  sections.forEach((sec, i) => {
    const li = document.createElement("li");
    li.textContent = `(${i + 1}) ${sec.question || sec.title || ""}`;
    if (i >= VISIBLE_STEPS) li.hidden = true;
    list.append(li);
  });
  const more = refs.preview.querySelector(".rw-more");
  if (sections.length > VISIBLE_STEPS) {
    more.hidden = false;
    more.onclick = () => {
      const expand = more.dataset.open !== "1";
      list.querySelectorAll("li").forEach((li, i) => {
        if (i >= VISIBLE_STEPS) li.hidden = !expand;
      });
      more.dataset.open = expand ? "1" : "0";
      more.textContent = expand ? "Less" : "More";
    };
  }
}

// Approval flow: staged preview first; "Start research" approves the plan
// as-is, "Edit plan" falls back to the full two-pane editor. Resolves with
// the approved (possibly edited) plan; the left pane ends up showing the
// locked plan either way.
function presentPlanForApproval(refs, plan) {
  refs.body.hidden = true;
  refs.preview.hidden = false;
  renderPlanPreview(refs, plan);
  return new Promise((resolve) => {
    refs.preview.querySelector(".rw-start").onclick = () => {
      refs.preview.hidden = true;
      refs.body.hidden = false;
      renderPlanEditor(refs, plan, false); // locked plan for the run
      resolve(plan);
    };
    refs.preview.querySelector(".rw-edit-plan").onclick = () => {
      refs.preview.hidden = true;
      refs.body.hidden = false;
      renderPlanForApproval(refs, plan).then(resolve);
    };
  });
}

function rwAppendFeedRow(refs, evt) {
  refs._steps.push(evt);
  if (!refs._feedHasRows) {
    refs.feed.innerHTML = "";
    refs._feedHasRows = true;
  }
  const failed = evt.status === "failed";
  const row = document.createElement("div");
  row.className = `rw-row ${failed ? "failed" : "ok"}`;
  const detail = evt.detail ? `<div class="rw-row-detail">${escapeHtml(String(evt.detail))}</div>` : "";
  row.innerHTML = `<span class="rw-row-ic">${failed ? RW_ICON_FAIL : RW_ICON_OK}</span>
    <div class="rw-row-body"><span class="rw-stage">${escapeHtml(evt.stage || "")}</span><span class="rw-row-title">${escapeHtml(evt.title || "")}</span>${detail}</div>`;
  refs.feed.append(row);
}

function rwAddSource(refs, src) {
  if (!src || !src.url || refs._sourceUrls.has(src.url)) return;
  refs._sourceUrls.add(src.url);
  refs._sources.push(src);
  if (refs._report) refs._report.sources = refs._sources;
  refs.sourcesBox.hidden = false;
  const host = rwHostname(src.url);
  const href = rwSafeHref(src.url);
  const a = document.createElement("a");
  a.className = "rw-source";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  if (href) a.href = href;
  a.innerHTML = `<img alt="" src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32">
    <span class="rw-source-text"><span class="rw-source-title">${escapeHtml(src.title || host)}</span><span class="rw-source-host">${escapeHtml(host)}</span></span>`;
  refs.sourcesList.append(a);
  refs.sourcesCount.textContent = String(refs._sourceUrls.size);
}

function applyResearchEvent(refs, evt) {
  switch (evt.type) {
    case "activity": {
      refs.current.hidden = false;
      refs.currentText.textContent = evt.title || "";
      refs.current.querySelector(".rw-spinner").style.visibility =
        evt.status === "started" ? "visible" : "hidden";
      if (evt.status === "ok" || evt.status === "failed") rwAppendFeedRow(refs, evt);
      break;
    }
    case "source":
      rwAddSource(refs, evt.source);
      break;
    case "report":
      // The report is the deliverable — it opens in the document canvas, and
      // the card collapses to its finished-state summary.
      refs.current.hidden = true;
      presentReport(refs, evt.markdown || "", evt.title);
      break;
    case "run_finished": {
      const s = evt.stats || {};
      // If a report was already presented (state === "report"), don't downgrade
      // back to "done" — that would un-hide .rw-body (the live plan/activity
      // grid, via the `[data-state="report"] .rw-body { display: none }` rule)
      // and make it render on top of the summary already appended below it.
      if (refs.root.dataset.state !== "report") refs.setState("done");
      refs.setStatus("Completed");
      refs._stats = s;
      rwRenderMeta(refs);
      refs.current.hidden = true;
      break;
    }
    case "title":
      // The backend auto-titled this research-first conversation; refresh the
      // sidebar so "New Conversation" is replaced with the generated title.
      if (evt.title) fetchConversations();
      break;
    case "error":
      rwAppendFeedRow(refs, { stage: "error", title: evt.message || "Error", status: "failed" });
      break;
    default:
      break; // run_started / plan: plan is already shown from the approval step
  }
  refs.feed.scrollTop = refs.feed.scrollHeight;
}

async function streamResearch(query, sessionId, plan, refs) {
  const res = await authFetch(`${BASE_URL}/api/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: query, conversation_id: sessionId, plan }),
  });
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => "");
    throw new Error("Research stream failed to start. " + t.slice(0, 200));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const handleLine = (line) => {
    const s = line.trim();
    if (!s) return;
    let evt;
    try { evt = JSON.parse(s); } catch { return; }
    applyResearchEvent(refs, evt);
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      handleLine(buffer.slice(0, nl));
      buffer = buffer.slice(nl + 1);
    }
  }
  handleLine(buffer);
}

async function handleDeepResearchSubmit(query) {
  const wasEmpty = chatWindow.querySelector(".message") === null;

  const userMessage = createMessage("user", query);
  chatWindow.append(userMessage);

  const { article, refs } = buildResearchWorkspace(query);
  chatWindow.append(article);

  syncStageState();
  setComposerBusy(true);
  window.requestAnimationFrame(() => {
    if (typeof scrollMessageToTop === "function") scrollMessageToTop(userMessage);
  });

  try {
    const sessionId = await ensureSession();
    if (wasEmpty) fetchConversations();

    // 1) Plan preview (single planning LLM call, no gathering).
    const planRes = await authFetch(`${BASE_URL}/api/research/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: query, conversation_id: sessionId }),
    });
    const planData = await planRes.json().catch(() => ({}));
    if (!planRes.ok || !planData.plan) {
      throw new Error(planData.error || "Could not build a research plan.");
    }

    // The backend auto-titles a still-"New Conversation" thread here, at plan
    // time, so the sidebar shows the real title while the plan is up for
    // approval rather than staying "New Conversation" until research runs.
    if (planData.title) fetchConversations();

    // 2) Let the user approve/edit the plan, then execute it.
    refs.setStatus("Review the plan");
    const approvedPlan = await presentPlanForApproval(refs, planData.plan);
    // The edit path resolves with a *modified* plan — keep the summary honest
    // about what actually ran, not what was originally proposed.
    refs._plan = approvedPlan;

    refs.setState("researching");
    refs.setStatus("Researching…");
    refs.feed.innerHTML = `<div class="rw-empty">Starting research…</div>`;
    refs._feedHasRows = false;

    await streamResearch(query, sessionId, approvedPlan, refs);
    // Same guard as the run_finished handler — never downgrade out of "report".
    if (refs.root.dataset.state !== "done" && refs.root.dataset.state !== "report") {
      refs.setState("done");
      refs.setStatus("Completed");
      refs.current.hidden = true;
    }
  } catch (err) {
    refs.setState("error");
    refs.setStatus("Error");
    rwAppendFeedRow(refs, { stage: "error", title: err.message || "Deep research failed.", status: "failed" });
  } finally {
    setComposerBusy(false);
  }
}

// ══════════════════════════════════════════════════════════════════════
// Document agent — interview → research → written document
// One card in the chat that mutates in place through three states:
//   asking      the interview, one question at a time (≤4 options each)
//   researching the live NDJSON activity feed, same events as research
//   document    collapsed, with the card that opens the finished document
// Backend contract: POST /api/document/next (repeatedly) then
// POST /api/document/stream.
// ══════════════════════════════════════════════════════════════════════
const DOC_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="13" x2="15" y2="13"></line><line x1="9" y1="17" x2="13" y2="17"></line></svg>`;

function buildDocumentWorkspace(topic) {
  const article = document.createElement("article");
  article.className = "message assistant research-msg animate-in";

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.innerHTML = LOVELACE_LOGO_SVG;
  article.append(avatar);

  const card = document.createElement("div");
  card.className = "message-card research-card";
  card.innerHTML = `
    <div class="rw dw" data-state="asking">
      <div class="rw-head">
        <div class="rw-head-title">
          <span class="rw-badge">Document</span>
          <span class="rw-query"></span>
        </div>
        <div class="rw-status"><span class="rw-status-dot"></span><span class="rw-status-text">Preparing…</span></div>
      </div>
      <div class="dw-ask" hidden>
        <div class="dw-progress"></div>
        <p class="dw-question"></p>
        <p class="dw-why"></p>
        <div class="dw-options"></div>
        <div class="dw-custom">
          <input class="dw-custom-input" type="text" placeholder="Something else — type it here">
          <button class="dw-custom-go" type="button">Use this</button>
        </div>
        <div class="dw-ask-actions"><button class="dw-skip" type="button">Skip this question</button></div>
      </div>
      <div class="dw-run" hidden>
        <div class="rw-current" hidden><span class="rw-spinner"></span><span class="rw-current-text"></span></div>
        <div class="rw-feed"><div class="rw-empty">Starting…</div></div>
        <div class="rw-asec rw-sources" hidden>
          <div class="rw-asec-head">Sources <span class="rw-asec-count rw-sources-count">0</span></div>
          <div class="rw-sources-list"></div>
        </div>
      </div>
      <div class="dw-done" hidden></div>
    </div>`;
  article.append(card);
  card.querySelector(".rw-query").textContent = topic;

  const root = card.querySelector(".rw");
  const refs = {
    article, card, root,
    statusText: root.querySelector(".rw-status-text"),
    ask: root.querySelector(".dw-ask"),
    progress: root.querySelector(".dw-progress"),
    questionEl: root.querySelector(".dw-question"),
    whyEl: root.querySelector(".dw-why"),
    optionsEl: root.querySelector(".dw-options"),
    customWrap: root.querySelector(".dw-custom"),
    customInput: root.querySelector(".dw-custom-input"),
    customGo: root.querySelector(".dw-custom-go"),
    skipBtn: root.querySelector(".dw-skip"),
    run: root.querySelector(".dw-run"),
    doneEl: root.querySelector(".dw-done"),
    current: root.querySelector(".rw-current"),
    currentText: root.querySelector(".rw-current-text"),
    feed: root.querySelector(".rw-feed"),
    sourcesBox: root.querySelector(".rw-sources"),
    sourcesList: root.querySelector(".rw-sources-list"),
    sourcesCount: root.querySelector(".rw-sources-count"),
    _sourceUrls: new Set(),
    _sources: [],
    _feedHasRows: false,
    // rwAppendFeedRow records every row here; the shared research helpers
    // assume it exists.
    _steps: [],
    _answered: [],
  };
  refs.setState = (s) => {
    root.dataset.state = s;
    refs.ask.hidden = s !== "asking";
    refs.run.hidden = s !== "researching";
    refs.doneEl.hidden = s !== "document";
  };
  refs.setStatus = (t) => { refs.statusText.textContent = t; };
  // "thinking" shows the header alone — the first question hasn't arrived yet,
  // and an empty question box would flash before it does.
  refs.setState("thinking");
  return { article, refs };
}

// Shows what the router took from the conversation instead of asking. Only
// rendered when there is something to show, which is never the case for a
// document started from the + menu.
function showCarriedOverContext(refs, answers) {
  const carried = (answers || []).filter((a) => a && a.source === "chat" && a.answer);
  if (!carried.length) return;

  const box = document.createElement("div");
  box.className = "dw-carried";
  const head = document.createElement("div");
  head.className = "dw-carried-head";
  head.textContent = "From your conversation";
  box.append(head);

  const list = document.createElement("ul");
  list.className = "dw-carried-list";
  carried.forEach((a) => {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.className = "dw-carried-label";
    label.textContent = a.id === "format" ? "Format" : a.question;
    const value = document.createElement("span");
    value.className = "dw-carried-value";
    value.textContent = a.id === "format" ? String(a.answer).toUpperCase() : a.answer;
    li.append(label, value);
    list.append(li);
  });
  box.append(list);
  refs.root.insertBefore(box, refs.ask);

  // Useful while the user is answering and while it researches; clutter on the
  // collapsed final card, which is about the document rather than the brief.
  const setState = refs.setState;
  refs.setState = (s) => {
    setState(s);
    box.hidden = s === "document";
  };
}

// Renders one question and resolves with the chosen answer string — or null if
// skipped. Same promise-gate pattern the research plan approval uses: the card
// waits on a click rather than the caller polling anything.
function askDocumentQuestion(refs, question, index, total) {
  refs.setState("asking");
  refs.setStatus(`Question ${index} of ${total}`);
  refs.progress.textContent = `Question ${index} of ${total}`;
  refs.questionEl.textContent = question.question || "";
  refs.whyEl.textContent = question.why || "";
  refs.whyEl.hidden = !question.why;
  refs.optionsEl.innerHTML = "";

  // Free text is offered per question — the backend marks the format question
  // allow_custom:false because only four formats can actually be rendered.
  const allowCustom = question.allow_custom !== false;
  refs.customWrap.hidden = !allowCustom;
  refs.customInput.value = "";

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      refs.optionsEl.querySelectorAll(".dw-option").forEach((b) => { b.disabled = true; });
      refs.customGo.onclick = null;
      refs.skipBtn.onclick = null;
      refs.customInput.onkeydown = null;
      resolve(value);
    };

    (question.options || []).forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dw-option";
      btn.innerHTML = `<span class="dw-option-label"></span><span class="dw-option-desc"></span>`;
      btn.querySelector(".dw-option-label").textContent = opt.label || "";
      const desc = btn.querySelector(".dw-option-desc");
      desc.textContent = opt.description || "";
      desc.hidden = !opt.description;
      btn.addEventListener("click", () => {
        btn.classList.add("is-chosen");
        // `value` is the machine form (the format codes); label is what the
        // user read. Send whichever the backend gave us.
        finish(opt.value || opt.label || "");
      });
      refs.optionsEl.append(btn);
    });

    refs.customGo.onclick = () => {
      const typed = refs.customInput.value.trim();
      if (typed) finish(typed);
    };
    refs.customInput.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); refs.customGo.onclick(); }
    };
    refs.skipBtn.onclick = () => finish(null);
  });
}

// Collapsed finished state: the card that opens the document to read, plus an
// explicit download button for the format chosen in the interview.
//
// The download is a button and not only an automatic save because the run takes
// minutes: by the time it finishes the user's click is long expired, and a
// browser may drop a programmatic download with no user activation behind it.
// Silently losing the file would make the format question look pointless, so
// delivery is always something the user can see and re-trigger.
function presentDocument(refs, doc) {
  refs.setState("document");
  refs.setStatus("Completed");
  refs.doneEl.innerHTML = "";

  const fmt = (doc.format || "md").toLowerCase();
  const note = document.createElement("p");
  note.className = "rw-done-note";
  note.textContent = "Document ready.";

  const card = document.createElement("button");
  card.type = "button";
  card.className = "rw-report-card";
  card.innerHTML = `<span class="rw-report-ic">${DOC_ICON}</span>
    <span class="rw-report-meta">
      <span class="rw-report-name"></span>
      <span class="rw-report-sub"></span>
    </span>`;
  card.querySelector(".rw-report-name").textContent = doc.title;
  card.querySelector(".rw-report-sub").textContent = `${fmt.toUpperCase()} · click to read`;
  doc.card = card;
  card.addEventListener("click", () => {
    if (activeReport && activeReport.card === card && !docCanvas.hidden) closeReportCanvas();
    else openReportCanvas(doc);
  });

  const actions = document.createElement("div");
  actions.className = "dw-deliver";
  const dl = document.createElement("button");
  dl.type = "button";
  dl.className = "dw-download";
  dl.textContent = `Download .${fmt}`;
  const status = document.createElement("span");
  status.className = "dw-deliver-status";
  actions.append(dl, status);

  dl.addEventListener("click", async () => {
    dl.disabled = true;
    const saved = await downloadReportFile(fmt, doc);
    dl.disabled = false;
    status.textContent = saved ? `Saved ${saved}` : "Download failed — try again";
  });

  // Lets the caller report the outcome of its own automatic attempt.
  refs._deliverStatus = status;
  refs.doneEl.append(note, card, actions);
  return card;
}

// Pulls the document title out of the markdown's H1 so the card and the file
// name match what the model actually titled it.
const docTitleFromMarkdown = (markdown, fallback) => {
  const line = (markdown || "").split("\n").find((l) => l.trim().startsWith("# "));
  return line ? line.trim().slice(2).trim() : (fallback || "Document");
};

async function streamDocument(brief, sessionId, refs, skipUserMessage = false) {
  const res = await authFetch(`${BASE_URL}/api/document/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: sessionId,
      brief,
      skip_user_message: skipUserMessage,
    }),
  });
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => "");
    throw new Error("Document generation failed to start. " + t.slice(0, 200));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let produced = null;

  const handleLine = (line) => {
    const s = line.trim();
    if (!s) return;
    let evt;
    try { evt = JSON.parse(s); } catch { return; }
    if (evt.type === "document") {
      produced = evt;
      return;
    }
    if (evt.type === "run_finished") {
      // Deliberately NOT delegated: applyResearchEvent's handler flips the card
      // to the research-specific "done" state, which is not one of this card's
      // three states and would blank it. presentDocument does the finishing.
      refs.current.hidden = true;
      return;
    }
    // The rest share the research event vocabulary (activity/source/title/error).
    applyResearchEvent(refs, evt);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      handleLine(buffer.slice(0, nl));
      buffer = buffer.slice(nl + 1);
    }
  }
  handleLine(buffer);
  return produced;
}

// `options` is how a document routed out of plain chat differs from one started
// from the + menu: the chat turn already rendered the user's bubble and already
// stored it, and it arrives with a brief the router seeded from the
// conversation rather than an empty one.
async function handleDocumentSubmit(topic, options = {}) {
  const {
    seededBrief = null,
    skipUserMessage = false,
    renderUserMessage = true,
    sessionId: presetSession = null,
  } = options;

  const wasEmpty = chatWindow.querySelector(".message") === null;

  let userMessage = null;
  if (renderUserMessage) {
    userMessage = createMessage("user", topic);
    chatWindow.append(userMessage);
  }

  const { article, refs } = buildDocumentWorkspace(topic);
  chatWindow.append(article);

  syncStageState();
  setComposerBusy(true);
  if (userMessage) {
    window.requestAnimationFrame(() => {
      if (typeof scrollMessageToTop === "function") scrollMessageToTop(userMessage);
    });
  }

  const brief = seededBrief
    ? {
        topic: seededBrief.topic || topic,
        format: seededBrief.format || "md",
        answers: Array.isArray(seededBrief.answers) ? seededBrief.answers : [],
        round: 1,
      }
    : { topic, format: "md", answers: [], round: 1 };

  // Anything the router lifted out of the conversation is shown before the
  // first question, so the user can see what was assumed on their behalf
  // instead of only noticing it in the finished document.
  showCarriedOverContext(refs, brief.answers);

  try {
    const sessionId = presetSession || await ensureSession();
    if (wasEmpty) fetchConversations();

    // 1) Interview. The brief travels with every call, so the server keeps no
    // session — and the round cap lives server-side, which is why this loop
    // trusts `ready` rather than counting rounds itself.
    for (let round = 1; ; round += 1) {
      brief.round = round;
      refs.setStatus("Thinking about what to ask…");
      const res = await authFetch(`${BASE_URL}/api/document/next`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: sessionId, brief }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.error || "Could not prepare questions.");
      // The server resolves the format itself when the request already named
      // one ("...as a PDF"), in which case it never asks.
      if (data.format) brief.format = data.format;
      if (data.ready || !(data.questions || []).length) break;

      const questions = data.questions;
      for (let i = 0; i < questions.length; i += 1) {
        const q = questions[i];
        const answer = await askDocumentQuestion(refs, q, i + 1, questions.length);
        brief.answers.push({ id: q.id, question: q.question, answer });
        // The format answer also selects the file the user gets at the end.
        if (q.id === "format" && answer) brief.format = answer;
        // A skipped format question still has to produce some file.
        if (q.id === "format" && !answer) brief.format = "pdf";
      }
    }

    // 2) Research + write.
    refs.setState("researching");
    refs.setStatus("Researching…");
    refs.feed.innerHTML = `<div class="rw-empty">Gathering sources…</div>`;
    refs._feedHasRows = false;

    const produced = await streamDocument(brief, sessionId, refs, skipUserMessage);
    if (!produced) throw new Error("The document stream ended without a document.");

    const doc = {
      title: docTitleFromMarkdown(produced.markdown, topic),
      markdown: produced.markdown || "",
      sources: produced.sources || refs._sources,
      format: produced.format || brief.format,
      card: null,
    };
    presentDocument(refs, doc);
    openReportCanvas(doc);
    // Try to deliver the chosen format straight away, and say what happened
    // either way — a browser that drops the automatic save leaves the button.
    const saved = await downloadReportFile(doc.format, doc);
    if (refs._deliverStatus) {
      refs._deliverStatus.textContent = saved
        ? `Saved ${saved}`
        : "Not downloaded automatically — use the button.";
    }
  } catch (err) {
    refs.setState("researching");
    refs.setStatus("Error");
    refs.current.hidden = true;
    rwAppendFeedRow(refs, {
      stage: "error", title: err.message || "Document generation failed.", status: "failed",
    });
  } finally {
    setComposerBusy(false);
  }
}

function replayDocumentTrace(trace, content, sources, messageId = null) {
  const brief = trace.brief || {};
  const { article, refs } = buildDocumentWorkspace(brief.topic || "Document");

  // Only sources are replayed, not the activity feed: the finished card shows
  // the document, and its live feed pane is hidden in that state — rebuilding
  // rows just to hide them would be wasted work. The sources still matter
  // because they travel with the document into the canvas.
  (trace.events || []).forEach((e) => {
    if (e.type === "source") rwAddSource(refs, e.source);
  });
  if (!refs._sourceUrls.size && Array.isArray(sources)) sources.forEach((s) => rwAddSource(refs, s));
  refs.current.hidden = true;

  const doc = {
    title: docTitleFromMarkdown(content, brief.topic),
    markdown: content || "",
    sources: refs._sources.length ? refs._sources : (sources || []),
    format: brief.format || "md",
    messageId,
    card: null,
  };
  // Replayed from history: show the card, but don't yank the canvas open.
  presentDocument(refs, doc);
  return article;
}

function replayResearchTrace(trace, content, sources, messageId = null) {
  let query = "";
  (trace.events || []).forEach((e) => { if (e.type === "run_started" && e.query) query = e.query; });
  if (!query && trace.plan && trace.plan.title) query = trace.plan.title;

  const { article, refs } = buildResearchWorkspace(query);
  if (trace.plan) renderPlanEditor(refs, trace.plan, false);
  else refs.planScroll.innerHTML = `<div class="rw-empty">No plan recorded.</div>`;

  refs.setState("done");
  refs.feed.innerHTML = "";
  refs._feedHasRows = true;
  (trace.events || []).forEach((e) => {
    if (e.type === "activity" && (e.status === "ok" || e.status === "failed")) rwAppendFeedRow(refs, e);
    else if (e.type === "source") rwAddSource(refs, e.source);
  });
  if (!refs.feed.children.length) refs.feed.innerHTML = `<div class="rw-empty">No activity recorded.</div>`;

  if (!refs._sourceUrls.size && Array.isArray(sources)) {
    sources.forEach((s) => rwAddSource(refs, s));
  }

  let stats = null;
  (trace.events || []).forEach((e) => { if (e.type === "run_finished") stats = e.stats; });
  refs._stats = stats || null;
  refs.setStatus("Completed");
  refs.current.hidden = true;

  // Replayed from history: show the card, but don't yank the canvas open
  // while the user is scrolling back through an old conversation.
  presentReport(refs, content || "", trace.plan && trace.plan.title, false, messageId);
  return article;
}

// ══════════════════════════════════════════════════════════════════════
// Report canvas — the finished deep-research report opens as a document
// pane beside the chat. The chat keeps a compact card that re-opens it,
// so a conversation can hold several reports and switch between them.
// ══════════════════════════════════════════════════════════════════════
const docCanvas = document.getElementById("docCanvas");
const dcTitle = document.getElementById("dcTitle");
const dcBody = document.getElementById("dcBody");
const dcScroll = document.getElementById("dcScroll");
const dcSources = document.getElementById("dcSources");
const dcSourcesList = document.getElementById("dcSourcesList");
const dcContentsBtn = document.getElementById("dcContentsBtn");
const dcContentsMenu = document.getElementById("dcContentsMenu");
const dcExportBtn = document.getElementById("dcExportBtn");
const dcExportMenu = document.getElementById("dcExportMenu");
const dcClose = document.getElementById("dcClose");

// The report currently rendered in the canvas: { title, markdown, sources, card }.
let activeReport = null;
// The artifact currently rendered in the canvas: the server's artifact dict
// plus { card }. Exactly one of activeReport / activeArtifact is non-null.
let activeArtifact = null;

const dcModes = document.getElementById("dcModes");
const dcModePreview = document.getElementById("dcModePreview");
const dcModeCode = document.getElementById("dcModeCode");
const dcContentsWrap = document.getElementById("dcContentsWrap");
const dcArtifact = document.getElementById("dcArtifact");
const dcFrame = document.getElementById("dcFrame");
const dcCodeWrap = document.getElementById("dcCodeWrap");
const dcCodeBody = document.getElementById("dcCodeBody");

const RW_ICON_REPORT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><line x1="16.5" y1="16.5" x2="21" y2="21"></line><line x1="8" y1="10" x2="14" y2="10"></line><line x1="8" y1="13" x2="12" y2="13"></line></svg>`;

const closeDocMenus = () => {
  [[dcContentsBtn, dcContentsMenu], [dcExportBtn, dcExportMenu]].forEach(([btn, menu]) => {
    if (!menu) return;
    menu.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  });
};

const toggleDocMenu = (btn, menu) => {
  const opening = menu.hidden;
  closeDocMenus();
  if (!opening) return;
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
};

// Builds the Contents dropdown from the headings the report actually rendered.
const buildContentsMenu = () => {
  dcContentsMenu.innerHTML = "";
  const heads = dcBody.querySelectorAll("h1, h2, h3");
  if (!heads.length) {
    dcContentsMenu.innerHTML = `<div class="dc-menu-empty">No sections in this report.</div>`;
    return;
  }
  heads.forEach((h, i) => {
    if (!h.id) h.id = `dc-h-${i}`;
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dc-menu-item";
    item.dataset.level = h.tagName === "H3" ? "3" : "2";
    item.textContent = h.textContent;
    item.title = h.textContent;
    item.addEventListener("click", () => {
      closeDocMenus();
      dcScroll.scrollTo({ top: h.offsetTop - 16, behavior: "smooth" });
    });
    dcContentsMenu.append(item);
  });
};

const renderCanvasSources = (sources) => {
  dcSourcesList.innerHTML = "";
  const list = (sources || []).filter((s) => s && s.url);
  dcSources.hidden = !list.length;
  const seen = new Set();
  list.forEach((s) => {
    if (seen.has(s.url)) return;
    seen.add(s.url);
    const host = rwHostname(s.url);
    const href = rwSafeHref(s.url);
    const a = document.createElement("a");
    a.className = "rw-source";
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    if (href) a.href = href;
    a.innerHTML = `<img alt="" src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32">
      <span class="rw-source-text"><span class="rw-source-title">${escapeHtml(s.title || host)}</span><span class="rw-source-host">${escapeHtml(host)}</span></span>`;
    dcSourcesList.append(a);
  });
};

function openReportCanvas(report) {
  activeReport = report;
  activeArtifact = null;
  setCanvasKind("report");
  dcModes.hidden = true;
  if (dcFrame) dcFrame.removeAttribute("srcdoc");
  dcTitle.textContent = report.title || "Research report";
  dcBody.innerHTML = parseMarkdown(report.markdown || "");
  renderCanvasSources(report.sources);
  buildContentsMenu();
  closeDocMenus();
  dcScroll.scrollTop = 0;
  docCanvas.hidden = false;
  pageShell.classList.add("canvas-open");
  document.querySelectorAll(".rw-report-card").forEach((c) => {
    c.classList.toggle("is-open", c === report.card);
  });
  document.querySelectorAll(".af-card").forEach((c) => c.classList.remove("is-open"));
}

function closeReportCanvas() {
  closeDocMenus();
  docCanvas.hidden = true;
  pageShell.classList.remove("canvas-open");
  activeReport = null;
  activeArtifact = null;
  // Tear down the frame so a running artifact's timers/animations stop
  // instead of ticking on invisibly behind the closed canvas.
  if (dcFrame) dcFrame.removeAttribute("srcdoc");
  document.querySelectorAll(".rw-report-card").forEach((c) => c.classList.remove("is-open"));
  document.querySelectorAll(".af-card").forEach((c) => c.classList.remove("is-open"));
}

// ══════════════════════════════════════════════════════════════════════
// Artifacts — self-contained deliverables (a runnable page or a code file)
// the assistant produces. They open in the same canvas as research reports;
// `data-kind` on the canvas selects the toolbar controls and body pane.
//
// SECURITY: artifact HTML is model-generated and must be treated as hostile.
// It runs in an iframe with sandbox="allow-scripts" and deliberately WITHOUT
// allow-same-origin — that pair would give the frame a real origin and let it
// remove its own sandbox, reach into this document, and read localStorage
// (where the session token lives). The sandbox attribute is written literally
// in lovelace.html and never touched from JS. On top of that, the CSP below
// is prepended to every artifact so it cannot make network requests.
// ══════════════════════════════════════════════════════════════════════

// Blocks every remote fetch (script, style, font, image, XHR, WebSocket) while
// still allowing the inline <style>/<script> a self-contained page needs.
// 'none' defaults mean anything not named here is denied.
const ARTIFACT_CSP =
  "default-src 'none'; " +
  "script-src 'unsafe-inline' 'unsafe-eval'; " +
  "style-src 'unsafe-inline'; " +
  "img-src data: blob:; " +
  "font-src data:; " +
  "media-src data: blob:; " +
  "connect-src 'none'; " +
  "form-action 'none'; " +
  "base-uri 'none';";

// The sandbox has no allow-same-origin, so the frame's origin is opaque and
// READING window.localStorage throws SecurityError before a single line of the
// artifact's own code runs — one unguarded `localStorage.getItem` is a blank
// panel. Models reach for it constantly for anything "saved" or "remembered",
// so rather than relying on the prompt alone, shadow the throwing accessors
// with in-memory equivalents. Data then lives for as long as the panel is open
// instead of killing the page.
//
// Object.defineProperty is what makes this work: it installs an own data
// property on window, shadowing the prototype accessor without ever invoking
// the getter that would throw.
const ARTIFACT_STORAGE_SHIM = `
<script>
(function () {
  function memoryStorage() {
    var data = Object.create(null);
    return {
      getItem: function (k) {
        return Object.prototype.hasOwnProperty.call(data, String(k)) ? data[String(k)] : null;
      },
      setItem: function (k, v) { data[String(k)] = String(v); },
      removeItem: function (k) { delete data[String(k)]; },
      clear: function () { data = Object.create(null); },
      key: function (i) { var ks = Object.keys(data); return i < ks.length ? ks[i] : null; },
      get length() { return Object.keys(data).length; }
    };
  }
  ["localStorage", "sessionStorage"].forEach(function (name) {
    try {
      Object.defineProperty(window, name, {
        value: memoryStorage(), configurable: true, writable: false
      });
    } catch (e) { /* nothing further we can do; the artifact must cope */ }
  });
})();
</script>`;

// Wrap the model's HTML so the CSP is the first thing the parser sees. A <meta>
// CSP only governs what comes after it, so it must precede any markup — hence
// building a fresh document rather than string-patching the model's <head>.
// The shim goes in <head> too: it has to be installed before the artifact's own
// <script> runs, wherever in the body that happens to be.
const buildArtifactDoc = (html) => `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${ARTIFACT_CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base target="_blank">
${ARTIFACT_STORAGE_SHIM}
</head><body>
${html}
</body></html>`;

const setCanvasKind = (kind) => {
  docCanvas.dataset.kind = kind;
  const isArtifact = kind === "artifact";
  dcScroll.hidden = isArtifact;
  dcArtifact.hidden = !isArtifact;
  if (dcContentsWrap) dcContentsWrap.hidden = isArtifact;
  // Every export action renders report markdown, so the whole menu is hidden
  // for artifacts rather than shown empty.
  const exportWrap = dcExportBtn.closest(".dc-menu-wrap");
  if (exportWrap) exportWrap.hidden = isArtifact;
};

// Preview shows the running page; Code shows highlighted source. Non-runnable
// artifacts (a .py file) are code-only, so the switch is hidden for them.
const setArtifactMode = (mode) => {
  if (!activeArtifact) return;
  const preview = mode === "preview" && activeArtifact.kind === "runnable";
  dcFrame.hidden = !preview;
  dcCodeWrap.hidden = preview;
  dcModePreview.classList.toggle("is-active", preview);
  dcModeCode.classList.toggle("is-active", !preview);
  dcModePreview.setAttribute("aria-selected", String(preview));
  dcModeCode.setAttribute("aria-selected", String(!preview));
};

function openArtifactCanvas(artifact) {
  activeArtifact = artifact;
  activeReport = null;
  setCanvasKind("artifact");

  dcTitle.textContent = artifact.title || "Artifact";

  // Source view — highlight.js if it knows the language, plain otherwise.
  // renderCode returns a full <pre><code>, so unwrap it into our own <pre>.
  const holder = document.createElement("div");
  holder.innerHTML = renderCode(escapeHtml(artifact.content || ""), artifact.language || "");
  dcCodeBody.innerHTML = holder.querySelector("code")?.innerHTML
    ?? escapeHtml(artifact.content || "");
  dcCodeBody.className = holder.querySelector("code")?.className || "";

  const runnable = artifact.kind === "runnable";
  dcModes.hidden = !runnable;
  if (runnable) {
    // Assigning srcdoc reloads the frame, so a re-open always starts the
    // artifact fresh rather than resuming previous state.
    dcFrame.srcdoc = buildArtifactDoc(artifact.content || "");
  } else {
    dcFrame.removeAttribute("srcdoc");
  }
  setArtifactMode(runnable ? "preview" : "code");

  closeDocMenus();
  docCanvas.hidden = false;
  pageShell.classList.add("canvas-open");
  document.querySelectorAll(".af-card").forEach((c) => {
    c.classList.toggle("is-open", c === artifact.card);
  });
  document.querySelectorAll(".rw-report-card").forEach((c) => c.classList.remove("is-open"));
}

// The chat-side card that opens an artifact, mirroring the research report card.
const AF_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>`;

function buildArtifactCard(artifact) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "af-card";
  const meta = artifact.kind === "runnable"
    ? "Interactive · click to open"
    : `${(artifact.language || artifact.type || "code").toUpperCase()} · click to open`;
  card.innerHTML = `<span class="af-card-ic">${AF_ICON}</span>
    <span class="af-card-meta">
      <span class="af-card-name"></span>
      <span class="af-card-sub"></span>
    </span>`;
  card.querySelector(".af-card-name").textContent = artifact.title || "Artifact";
  card.querySelector(".af-card-sub").textContent = meta;

  // Say why an app stops mid-feature or forgets its data, rather than leaving
  // the user to discover it by using the thing. Truncation is the more serious
  // of the two, so it wins when somehow both are set.
  const notice = artifact.truncated
    ? "Cut off before it finished — ask to continue it"
    : artifact.uses_storage
      ? "Saves data for this session only — resets when reopened"
      : "";
  if (notice) {
    const el = document.createElement("span");
    el.className = "af-card-note";
    el.textContent = notice;
    card.querySelector(".af-card-meta").append(el);
  }

  artifact.card = card;
  card.addEventListener("click", () => {
    if (activeArtifact === artifact && !docCanvas.hidden) closeReportCanvas();
    else openArtifactCanvas(artifact);
  });
  return card;
}

// The export button's normal label, restored after a transient "Copied".
const EXPORT_BTN_HTML = `Share &amp; Export <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

// Markdown → plain text for the "Copy as text" export.
const reportPlainText = (markdown) => {
  const tmp = document.createElement("div");
  tmp.innerHTML = parseMarkdown(markdown || "");
  return (tmp.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
};

// Flash a transient label on the export button, then restore it.
const flashExportBtn = (label, ms = 1400) => {
  dcExportBtn.textContent = label;
  setTimeout(() => { dcExportBtn.innerHTML = EXPORT_BTN_HTML; }, ms);
};

// Saves a Blob under `filename` via a throwaway object URL.
const saveBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Revoke on the next tick — Firefox cancels the download if the URL dies
  // before it starts reading.
  setTimeout(() => URL.revokeObjectURL(url), 5000);
};

// Reads the filename the server chose, falling back to the report title.
const filenameFromResponse = (res, fallback) => {
  const header = res.headers.get("Content-Disposition") || "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  return match ? decodeURIComponent(match[1]) : fallback;
};

// Deep-research report → .md/.txt/.docx/.pdf. Rendering happens server-side
// (backend/agents/generator_agent.py) because .docx and .pdf are real binary
// container formats, not something worth hand-rolling in the browser. Reports
// replayed from history are exported by message id so the file matches what is
// stored; a just-finished run has no row id yet and posts its markdown.
// `report` defaults to whatever the canvas has open; the document agent passes
// its result explicitly so the download can start in the same tick the canvas
// opens, without depending on that assignment having landed first.
const downloadReportFile = async (fmt, report = null) => {
  const target = report || activeReport;
  if (!target) return;
  const { title, markdown, sources, messageId } = target;
  const fallbackName =
    `${(title || "research-report").replace(/[^\w\-]+/g, "-").slice(0, 60) || "research-report"}.${fmt}`;

  dcExportBtn.textContent = "Preparing…";
  try {
    const res = await authFetch(`${BASE_URL}/api/documents/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: activeSessionId,
        format: fmt,
        message_id: messageId ?? null,
        markdown: messageId ? "" : (markdown || ""),
        title: title || "",
        sources: Array.isArray(sources) ? sources : [],
      }),
    });
    if (!res.ok) {
      let detail = `Export failed (${res.status})`;
      try {
        const body = await res.json();
        detail = body.detail || body.error || detail;
      } catch (err) { /* non-JSON error body — keep the status text */ }
      throw new Error(detail);
    }
    const filename = filenameFromResponse(res, fallbackName);
    saveBlob(await res.blob(), filename);
    flashExportBtn("Downloaded");
    return filename;
  } catch (err) {
    console.error("Report export failed:", err);
    flashExportBtn("Export failed", 2200);
    return null;
  }
};

// Every action operates on the open report; the menu is unreachable otherwise.
const runExportAction = async (action) => {
  if (!activeReport) return;
  const { markdown } = activeReport;
  if (action === "copy-text" || action === "copy-md") {
    const text = action === "copy-md" ? markdown || "" : reportPlainText(markdown);
    try {
      await navigator.clipboard.writeText(text);
      flashExportBtn("Copied");
    } catch (err) {
      console.error("Copy failed:", err);
    }
  } else if (action.startsWith("download-")) {
    await downloadReportFile(action.slice("download-".length));
  }
};

if (docCanvas) {
  dcContentsBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleDocMenu(dcContentsBtn, dcContentsMenu); });
  dcExportBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleDocMenu(dcExportBtn, dcExportMenu); });
  dcExportMenu.addEventListener("click", (e) => {
    const item = e.target.closest(".dc-menu-item");
    if (!item) return;
    closeDocMenus();
    runExportAction(item.dataset.action);
  });
  dcModePreview.addEventListener("click", () => setArtifactMode("preview"));
  dcModeCode.addEventListener("click", () => setArtifactMode("code"));
  dcClose.addEventListener("click", closeReportCanvas);
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".dc-menu-wrap")) closeDocMenus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!dcContentsMenu.hidden || !dcExportMenu.hidden) closeDocMenus();
    else if (!docCanvas.hidden) closeReportCanvas();
  });
}

// ── Finished-state summary ────────────────────────────────────────────────
// Once the report exists the live two-pane workspace is done: it collapses to
// a single quiet block — one completion line, the report card, a stat line,
// and one "Research details" disclosure holding Plan, Steps and Sources.
// Nothing here duplicates the report itself.
const RW_ICON_CARET = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"></polyline></svg>`;

// The run's numbers as one line. Called again on run_finished, which lands
// after the report event and carries rounds/elapsed.
function rwRenderMeta(refs) {
  if (!refs._metaEl) return;
  const s = refs._stats || {};
  const bits = [
    `${refs._sources.length} source${refs._sources.length === 1 ? "" : "s"}`,
    `${refs._steps.length} step${refs._steps.length === 1 ? "" : "s"}`,
  ];
  if (s.rounds) bits.push(`${s.rounds} round${s.rounds === 1 ? "" : "s"}`);
  if (s.elapsed_s) bits.push(`${s.elapsed_s}s`);
  refs._metaEl.textContent = bits.join(" · ");
}

// Read-only plan: plain text, not the editor's input/textarea fields.
function rwPlanSummaryEl(plan) {
  const wrap = document.createElement("div");
  wrap.className = "rw-sum-plan";
  const sections = (plan && plan.sections) || [];
  if (!sections.length) {
    wrap.innerHTML = `<div class="rw-empty">No plan recorded.</div>`;
    return wrap;
  }
  sections.forEach((sec, i) => {
    const row = document.createElement("div");
    row.className = "rw-sum-sec";
    row.innerHTML = `<span class="rw-sum-num">${i + 1}</span>
      <div class="rw-sum-sec-body">
        <div class="rw-sum-sec-title">${escapeHtml(sec.title || sec.question || "")}</div>
        <div class="rw-sum-sec-q"></div>
      </div>`;
    const q = row.querySelector(".rw-sum-sec-q");
    if (sec.question && sec.question !== sec.title) q.textContent = sec.question;
    else q.remove();
    wrap.append(row);
  });
  return wrap;
}

function rwStepsSummaryEl(steps) {
  const wrap = document.createElement("div");
  wrap.className = "rw-sum-steps";
  if (!steps.length) {
    wrap.innerHTML = `<div class="rw-empty">No activity recorded.</div>`;
    return wrap;
  }
  steps.forEach((evt) => {
    const failed = evt.status === "failed";
    const row = document.createElement("div");
    row.className = `rw-row ${failed ? "failed" : "ok"}`;
    row.innerHTML = `<span class="rw-row-ic">${failed ? RW_ICON_FAIL : RW_ICON_OK}</span>
      <div class="rw-row-body"><span class="rw-stage">${escapeHtml(evt.stage || "")}</span><span class="rw-row-title">${escapeHtml(evt.title || "")}</span></div>`;
    wrap.append(row);
  });
  return wrap;
}

function rwSourcesSummaryEl(sources) {
  const wrap = document.createElement("div");
  wrap.className = "rw-sum-sources";
  if (!sources.length) {
    wrap.innerHTML = `<div class="rw-empty">No sources recorded.</div>`;
    return wrap;
  }
  sources.forEach((src) => {
    const host = rwHostname(src.url);
    const href = rwSafeHref(src.url);
    const a = document.createElement("a");
    a.className = "rw-source";
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    if (href) a.href = href;
    a.innerHTML = `<img alt="" src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32">
      <span class="rw-source-text"><span class="rw-source-title">${escapeHtml(src.title || host)}</span><span class="rw-source-host">${escapeHtml(host)}</span></span>`;
    wrap.append(a);
  });
  return wrap;
}

// A single "Research details" disclosure. Inside it, three options —
// Plan / Sources / Steps — share one view, so the collapsed card stays one
// click away and only one body is ever on screen.
function rwBuildSummary(refs) {
  const box = document.createElement("div");
  box.className = "rw-sum";
  box.innerHTML = `
    <div class="rw-sum-bar">
      <button class="rw-sum-toggle" type="button" aria-expanded="false">
        <span class="rw-sum-caret">${RW_ICON_CARET}</span>
        <span class="rw-sum-toggle-text">Research details</span>
      </button>
      <span class="rw-sum-meta"></span>
    </div>
    <div class="rw-sum-panel" hidden></div>`;

  const panel = box.querySelector(".rw-sum-panel");
  const toggle = box.querySelector(".rw-sum-toggle");

  // Three views inside the disclosure; only one renders at a time.
  const views = [
    { id: "plan", label: "Plan", build: () => rwPlanSummaryEl(refs._plan),
      count: () => (refs._plan && refs._plan.sections || []).length },
    { id: "sources", label: "Sources", build: () => rwSourcesSummaryEl(refs._sources),
      count: () => refs._sources.length },
    { id: "steps", label: "Steps", build: () => rwStepsSummaryEl(refs._steps),
      count: () => refs._steps.length },
  ];

  panel.innerHTML = `<div class="rw-sum-tabs" role="tablist"></div><div class="rw-sum-view"></div>`;
  const tabRow = panel.querySelector(".rw-sum-tabs");
  const view = panel.querySelector(".rw-sum-view");

  const showView = (id) => {
    const v = views.find((x) => x.id === id) || views[0];
    tabRow.querySelectorAll(".rw-tab").forEach((t) => {
      const on = t.dataset.tab === v.id;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", String(on));
    });
    view.innerHTML = "";
    view.append(v.build());
    view.scrollTop = 0;
  };

  views.forEach((v) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "rw-tab";
    tab.dataset.tab = v.id;
    tab.setAttribute("role", "tab");
    const n = v.count();
    tab.innerHTML = `<span>${v.label}</span>${n ? `<span class="rw-tab-count">${n}</span>` : ""}`;
    tab.addEventListener("click", () => showView(v.id));
    tabRow.append(tab);
  });

  toggle.addEventListener("click", () => {
    const opening = panel.hidden;
    toggle.setAttribute("aria-expanded", String(opening));
    toggle.classList.toggle("is-open", opening);
    panel.hidden = !opening;
    // Always reopen on Plan — the run reads plan → sources → steps.
    if (opening) showView("plan");
  });

  refs._metaEl = box.querySelector(".rw-sum-meta");
  rwRenderMeta(refs);
  return box;
}

// Swaps the live two-pane workspace for the finished-report presentation.
// Opens the canvas unless replaying history.
function presentReport(refs, markdown, title, autoOpen = true, messageId = null) {
  if (refs._reportCard) {
    refs._reportCard.dataset.markdown = markdown || "";
    return refs._reportCard;
  }
  const report = {
    title: title || refs.root.querySelector(".rw-plan-title")?.value || "Research report",
    markdown: markdown || "",
    sources: refs._sources,
    // Set only when replaying from history; a live run has no row id yet, so
    // its export posts the markdown instead (see runExportAction).
    messageId,
    card: null,
  };
  refs._report = report;

  const done = document.createElement("div");
  done.className = "rw-done";

  const note = document.createElement("p");
  note.className = "rw-done-note";
  note.textContent = "Research complete. Open the report to read it — or ask a follow-up.";

  const wrap = document.createElement("div");
  wrap.className = "rw-report-wrap";
  const card = document.createElement("button");
  card.type = "button";
  card.className = "rw-report-card";
  const stamp = new Date().toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
  card.innerHTML = `<span class="rw-report-ic">${RW_ICON_REPORT}</span>
    <span class="rw-report-meta">
      <span class="rw-report-name"></span>
      <span class="rw-report-sub">${escapeHtml(stamp)}</span>
    </span>`;
  card.querySelector(".rw-report-name").textContent = report.title;
  report.card = card;
  card.addEventListener("click", () => {
    // Clicking the card of the report already on screen closes the canvas.
    if (activeReport && activeReport.card === card && !docCanvas.hidden) closeReportCanvas();
    else openReportCanvas(report);
  });
  wrap.append(card);

  done.append(note, wrap, rwBuildSummary(refs));
  refs.root.append(done);
  refs.setState("report");
  refs._reportCard = card;
  if (autoOpen) openReportCanvas(report);
  return card;
}

const animateLayoutShift = (element, firstRect, duration = 320) => {
  if (!firstRect) {
    return;
  }

  const lastRect = element.getBoundingClientRect();
  const deltaX = firstRect.left - lastRect.left;
  const deltaY = firstRect.top - lastRect.top;

  if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
    return;
  }

  element.animate(
    [
      { transform: `translate(${deltaX}px, ${deltaY}px)` },
      { transform: "translate(0, 0)" }
    ],
    {
      duration,
      easing: "cubic-bezier(0.2, 0.9, 0.2, 1)"
    }
  );
};

const syncPanelToggles = () => {
  const leftCollapsed = pageShell.classList.contains("left-collapsed");

  leftPanelToggle.classList.toggle("is-collapsed", leftCollapsed);
  leftPanelToggle.setAttribute("aria-label", leftCollapsed ? "Show left panel" : "Hide left panel");
  leftPanelToggle.setAttribute("title", leftCollapsed ? "Show left panel" : "Hide left panel");
  leftPanelToggle.innerHTML = createPanelIcon(leftCollapsed);
};

// Closes the + (attachment) menu, which now also hosts the Deep Research toggle.
const closeAgentMenu = () => {
  if (attachmentMenu) attachmentMenu.hidden = true;
  if (attachmentTrigger) {
    attachmentTrigger.classList.remove("is-open");
    attachmentTrigger.setAttribute("aria-expanded", "false");
  }
};

const closeAccountMenu = () => {
  accountPopover.classList.remove("is-open");
  profileMenuButton.setAttribute("aria-expanded", "false");
  profileMenu.setAttribute("aria-hidden", "true");
};

const toggleAccountMenu = () => {
  const isOpening = !accountPopover.classList.contains("is-open");
  closeAgentMenu();
  closeHistoryMenus();
  accountPopover.classList.toggle("is-open", isOpening);
  profileMenuButton.setAttribute("aria-expanded", String(isOpening));
  profileMenu.setAttribute("aria-hidden", String(!isOpening));
};

// The single currently-open menu, remembered so it can be hidden and returned
// to its row on close: { menu, home, button }.
let activeHistoryMenu = null;

// A transparent full-screen backdrop shown behind the open menu. It blocks all
// other interaction (including OTHER rows' three-dots) while a menu is open, so
// the first click anywhere just closes the current menu — the user must close
// it before another conversation's options become accessible.
let historyMenuBackdrop = null;
const getHistoryMenuBackdrop = () => {
  if (!historyMenuBackdrop) {
    historyMenuBackdrop = document.createElement("div");
    historyMenuBackdrop.className = "history-menu-backdrop";
    historyMenuBackdrop.hidden = true;
    historyMenuBackdrop.addEventListener("click", (e) => {
      e.stopPropagation();
      closeHistoryMenus();
    });
    document.body.appendChild(historyMenuBackdrop);
  }
  return historyMenuBackdrop;
};

const closeHistoryMenus = () => {
  document.querySelectorAll(".history-more.is-open").forEach((button) => {
    button.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
    const row = button.closest(".history-row");
    if (row) row.style.zIndex = "";
  });
  if (historyMenuBackdrop) historyMenuBackdrop.hidden = true;
  if (activeHistoryMenu) {
    const { menu, home } = activeHistoryMenu;
    menu.hidden = true;
    // Return it to its row's actions container (it was portalled to <body>).
    if (home && menu.parentElement !== home) home.appendChild(menu);
    activeHistoryMenu = null;
  }
};

// Open the conversation-options menu to the RIGHT of the three-dots button.
// The menu is portalled to <body> because the sidebar's backdrop-filter makes
// it the containing block for position:fixed AND the history list clips
// overflow — both would otherwise trap/hide the menu. In <body> it's truly
// viewport-positioned, so getBoundingClientRect coordinates are correct and
// nothing clips it. Flips to the left / clamps vertically when it would spill
// off-screen.
const openHistoryMenu = (button, menu) => {
  getHistoryMenuBackdrop().hidden = false; // block interaction with other rows
  const home = menu.parentElement;   // its row's .history-actions (to restore later)
  document.body.appendChild(menu);
  menu.hidden = false;               // must be visible to measure its size

  const gap = 8;
  const btn = button.getBoundingClientRect();
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;

  let left = btn.right + gap;
  let flippedLeft = false;
  if (left + mw > window.innerWidth - 8) { left = btn.left - gap - mw; flippedLeft = true; } // flip left
  left = Math.max(8, left);

  // Adaptive vertical: open downward from the dots when there's room below
  // (row near the top), otherwise flip and open upward (row near the bottom).
  let top;
  let openedUp = false;
  if (btn.top + mh <= window.innerHeight - 8) {
    top = btn.top;             // anchor menu top to the dots → extends down
  } else {
    top = btn.bottom - mh;     // anchor menu bottom to the dots → extends up
    openedUp = true;
  }
  top = Math.max(8, Math.min(top, window.innerHeight - mh - 8));

  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  // Grow the open animation from the corner nearest the dots.
  menu.style.transformOrigin = `${openedUp ? "bottom" : "top"} ${flippedLeft ? "right" : "left"}`;

  activeHistoryMenu = { menu, home, button };
};

profileMenuButton.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleAccountMenu();
});

leftPanelToggle.addEventListener("click", () => {
  pageShell.classList.toggle("left-collapsed");
  syncPanelToggles();
});

// highlight.js ships one stylesheet per theme, so the light/dark pair is
// swapped by enabling one <link> and disabling the other. Driven off the
// data-theme attribute rather than the toggle handler, so it stays correct
// no matter which code path changes the theme (including the initial load).
const syncCodeTheme = () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const light = document.getElementById("hljsLight");
  const darkSheet = document.getElementById("hljsDark");
  if (!light || !darkSheet) return;
  light.disabled = dark;
  darkSheet.disabled = !dark;
};
syncCodeTheme();
new MutationObserver(syncCodeTheme).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ["data-theme"],
});

themeToggleCheckbox.addEventListener("change", (e) => {
  const isDark = e.target.checked;
  const theme = isDark ? "dark" : "light";

  if (!document.startViewTransition) {
    document.documentElement.setAttribute("data-theme", theme);
    return;
  }

  const rect = e.target.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;

  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y)
  );

  document.documentElement.classList.add("theme-transition");

  const transition = document.startViewTransition(() => {
    document.documentElement.setAttribute("data-theme", theme);
  });

  transition.ready.then(() => {
    document.documentElement.animate(
      {
        clipPath: [
          `circle(0px at ${x}px ${y}px)`,
          `circle(${endRadius}px at ${x}px ${y}px)`
        ],
      },
      {
        duration: 500,
        easing: "ease-out",
        pseudoElement: "::view-transition-new(root)",
      }
    );
  });

  transition.finished.then(() => {
    document.documentElement.classList.remove("theme-transition");
  });
});

historyMoreButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const menu = button.parentElement.querySelector(".history-menu");
    const isOpening = menu.hidden;
    closeHistoryMenus();
    if (isOpening) {
      button.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
      openHistoryMenu(button, menu);
    }
  });
});

if (deepResearchToggle) {
  deepResearchToggle.addEventListener("click", () => {
    // Toggle Deep Research on/off from inside the + menu.
    setActiveMode(activeMode === DEEP_MODE ? CHAT_MODE : DEEP_MODE);
  });
}

if (artifactToggle) {
  artifactToggle.addEventListener("click", () => {
    // Same toggle semantics as Deep Research; setting one mode replaces the
    // other, so the two can never be active at once.
    setActiveMode(activeMode === ARTIFACT_MODE ? CHAT_MODE : ARTIFACT_MODE);
  });
}

if (documentToggle) {
  documentToggle.addEventListener("click", () => {
    setActiveMode(activeMode === DOC_MODE ? CHAT_MODE : DOC_MODE);
  });
}

modeChipClose.addEventListener("click", (event) => {
  event.stopPropagation();
  setActiveMode(CHAT_MODE);
});

historyItems.forEach((item) => {
  item.addEventListener("click", () => {
    historyItems.forEach((entry) => entry.classList.remove("selected"));
    item.classList.add("selected");
  });
});

promptInput.addEventListener("input", autoResize);
promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.addEventListener("click", (event) => {
  // The menu is portalled to <body> when open, so it's no longer inside
  // .history-actions — also exempt .history-menu so clicking inside it doesn't
  // self-close before a button acts.
  if (!event.target.closest(".history-actions") && !event.target.closest(".history-menu")) {
    closeHistoryMenus();
  }
  if (!event.target.closest(".account-popover")) {
    closeAccountMenu();
  }
  if (!event.target.closest(".msg-more-container")) {
    document.querySelectorAll(".msg-more-dropdown").forEach(d => d.hidden = true);
  }
  if (!event.target.closest(".msg-sources-container")) {
    document.querySelectorAll(".msg-sources-dropdown").forEach(d => d.hidden = true);
  }
  if (!event.target.closest(".attachment-selector")) {
    closeAgentMenu();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAgentMenu();
    closeHistoryMenus();
    closeAccountMenu();
  }
});

// Escapes HTML metacharacters so untrusted text (LLM output, which itself
// may echo scraped web content) can't break out into live DOM/script when
// later assigned via innerHTML (SEC-05).
const escapeHtml = (str) => String(str ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[c]));

// Exact inverse of escapeHtml. parseMarkdown escapes the whole document up
// front, but KaTeX and highlight.js need the original characters (`<`, `&`,
// quotes) to parse correctly — both emit their own markup and escape any text
// they don't wrap, so this does not reopen the SEC-05 injection path.
// `&amp;` is undone last so "&amp;lt;" can't collapse into a real "<".
const unescapeHtml = (str) => String(str ?? "")
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&amp;/g, "&");

// Inline formatting applied to already-HTML-escaped text: code spans, bold,
// italic, and safe links. Order matters — inline code is pulled out first so
// its contents aren't re-processed, then bold before italic so `**` isn't
// mistaken for a pair of single `*`.
const parseInline = (text) => {
  // Code spans and rendered math are stashed behind placeholders so the
  // bold/italic passes below can't reprocess their contents — KaTeX's markup
  // is full of `_` and `*`-adjacent class names that __bold__ would corrupt.
  const stash = [];
  const keep = (html) => "\u0000" + (stash.push(html) - 1) + "\u0000";
  let t = text;
  t = t.replace(/`([^`]+)`/g, (_m, c) => keep(`<code>${c}</code>`));
  // Inline math: $...$. Guards against prose that merely contains dollar
  // signs — the opening $ must be followed by a non-space, the closing $ must
  // not be preceded by one, and a digit after the closing $ rejects the match,
  // so "costs $5 and $10" stays literal while "$E = mc^2$" renders.
  t = t.replace(/\$(?!\s)((?:[^$\n\\]|\\.)+?)(?<!\s)\$(?!\d)/g,
    (_m, tex) => keep(renderMath(tex, false)));
  t = t.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/__([^_]+?)__/g, '<strong>$1</strong>');
  // Italic: the opening * must be followed by a non-space (real Markdown never
  // starts emphasis with whitespace) so "3 * 4 * 6" math isn't italicized.
  t = t.replace(/(^|[^*])\*([^*\s][^*\n]*?)\*(?!\*)/g, '$1<em>$2</em>');
  // Links: [text](url) — the url is already escaped; only http(s)/mailto are
  // allowed so an escaped `javascript:` can never become a live href (SEC-05).
  t = t.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  // Restore stashed code spans / rendered math.
  t = t.replace(/\u0000(\d+)\u0000/g, (_m, i) => stash[+i]);
  return t;
};

// Models vary wildly in how they format lists — some flatten a whole list onto
// a single line instead of using newlines. These pre-passes re-expand the two
// common flattened forms so the block parser downstream sees real lists. Both
// skip fenced code so code samples are never touched.

// Bullets: "intro: * Item A * Item B * Item C". A "*"/"•" followed by a space
// is a bullet marker, never italic (italic has no space after the opening *),
// so when a line packs 2+ of them we split each onto its own "- " line. Guard:
// ignore digit-led markers so "3 * 4" math isn't split.
const normalizeInlineBullets = (raw) => {
  let inFence = false;
  return raw.split(/\r?\n/).map((line) => {
    if (/^```/.test(line)) { inFence = !inFence; return line; }
    if (inFence) return line;
    const markers = line.match(/(?:^|[ \t])[*•‣◦][ \t]+[^\s\d*•‣◦]/g) || [];
    if (markers.length < 2) return line;
    return line
      .replace(/[ \t]+[*•‣◦][ \t]+/g, '\n- ')
      .replace(/^[*•‣◦][ \t]+/, '- ');
  }).join('\n');
};

// Ordered: "Steps: 1. First 2. Second 3. Third". Only split when the numbers
// form a consecutive run starting at 1 — that's a real flattened list, whereas
// prose like "in 1990. later 2000." is not — so years/sentence numbers are
// left alone.
const normalizeInlineOrdered = (raw) => {
  let inFence = false;
  return raw.split(/\r?\n/).map((line) => {
    if (/^```/.test(line)) { inFence = !inFence; return line; }
    if (inFence) return line;
    const nums = [...line.matchAll(/(?:^|\s)(\d+)[.)]\s+\S/g)].map((x) => +x[1]);
    if (nums.length < 2 || !nums.every((n, i) => n === i + 1)) return line;
    return line.replace(/\s+(\d+[.)]\s+)/g, '\n$1');
  }).join('\n');
};

// GitHub-style table helpers.
const mdSplitRow = (row) => {
  let r = row.trim();
  if (r.startsWith('|')) r = r.slice(1);
  if (r.endsWith('|')) r = r.slice(0, -1);
  return r.split('|').map((c) => c.trim());
};
// A separator row: pipes + dashes (with optional alignment colons), e.g.
// "| --- | :--: |". Requires a pipe so a plain "---" horizontal rule isn't
// mistaken for one.
const mdIsTableSep = (line) => /\|/.test(line) && /-/.test(line) && /^[\s|:-]+$/.test(line);

// ── Math (KaTeX) and code highlighting (highlight.js) ────────────────────
// Both libraries are vendored under frontend/vendor and loaded before this
// file. Every call is guarded so the app degrades to plain text if a library
// fails to load rather than throwing mid-render.

// Renders one math expression to HTML. `src` arrives HTML-escaped (parseMarkdown
// escapes up front), so it is unescaped here before being handed to KaTeX —
// KaTeX parses a math grammar and emits its own markup, so this does not
// reintroduce an injection path. Invalid math falls back to the literal text.
const renderMath = (src, display) => {
  const tex = unescapeHtml(src);
  if (typeof katex === "undefined") return escapeHtml(display ? `$$${tex}$$` : `$${tex}$`);
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: false,
      strict: false,
    });
  } catch {
    return escapeHtml(tex);
  }
};

// Highlights a fenced code block. `code` is already escaped; highlight.js needs
// the raw text, and re-escapes whatever it doesn't wrap in its own spans.
const renderCode = (code, lang) => {
  const raw = unescapeHtml(code);
  const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
  if (typeof hljs === "undefined") return `<pre><code${cls}>${code}</code></pre>`;
  try {
    const res = (lang && hljs.getLanguage(lang))
      ? hljs.highlight(raw, { language: lang })
      : hljs.highlightAuto(raw);
    return `<pre><code class="hljs${lang ? ` language-${escapeHtml(lang)}` : ""}">${res.value}</code></pre>`;
  } catch {
    return `<pre><code${cls}>${code}</code></pre>`;
  }
};

// Line-based Markdown → HTML. Produces real block elements (headings,
// paragraphs, lists, tables, code, blockquotes) so spacing is controlled by
// CSS margins, NOT by stacking a <br> per newline — which is what previously
// left several blank lines between a heading and its text. Written to tolerate
// the formatting quirks of many models (gemma, deepseek, qwen, llama, …).
const parseMarkdown = (rawText) => {
  if (!rawText) return "";
  // Escape FIRST so raw text can never contain real tags; every tag
  // introduced below this point is one we wrote, not attacker-controlled (SEC-05).
  const normalized = normalizeInlineOrdered(normalizeInlineBullets(rawText));
  const lines = escapeHtml(normalized).split(/\r?\n/);

  const out = [];
  let para = [];          // buffered soft-wrapped lines of the current paragraph
  let listType = null;    // 'ul' | 'ol' while inside a list
  let listItems = [];
  let quote = [];         // buffered blockquote lines
  let inCode = false;     // inside a ``` fenced block
  let code = [];
  let codeLang = '';      // language tag from the opening fence, if any

  const flushPara = () => {
    if (para.length) { out.push(`<p>${parseInline(para.join('<br>'))}</p>`); para = []; }
  };
  const flushList = () => {
    if (listType) {
      out.push(`<${listType}>${listItems.map((li) => `<li>${parseInline(li)}</li>`).join('')}</${listType}>`);
      listType = null; listItems = [];
    }
  };
  const flushQuote = () => {
    if (quote.length) { out.push(`<blockquote>${parseInline(quote.join('<br>'))}</blockquote>`); quote = []; }
  };
  const flushAll = () => { flushPara(); flushList(); flushQuote(); };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced code block toggle (``` optionally followed by a language tag).
    if (/^```/.test(line)) {
      if (inCode) {
        out.push(renderCode(code.join('\n'), codeLang)); code = []; codeLang = ''; inCode = false;
      } else {
        flushAll();
        inCode = true;
        codeLang = (line.match(/^```\s*([A-Za-z0-9+#_-]+)/) || [])[1] || '';
      }
      continue;
    }
    if (inCode) { code.push(line); continue; }

    // Blank line ends the current block.
    if (/^\s*$/.test(line)) { flushAll(); continue; }

    // Display math: a whole line of $$...$$, or a $$ ... $$ block spanning
    // several lines. Checked before headings so "$$" can't be misread.
    if (/^\s*\$\$/.test(line)) {
      flushAll();
      const single = line.match(/^\s*\$\$(.+?)\$\$\s*$/);
      if (single) { out.push(renderMath(single[1], true)); continue; }
      const buf = [line.replace(/^\s*\$\$/, '')];
      let j = i + 1;
      while (j < lines.length && !/\$\$/.test(lines[j])) { buf.push(lines[j]); j++; }
      if (j < lines.length) buf.push(lines[j].replace(/\$\$.*$/, ''));
      out.push(renderMath(buf.join('\n').trim(), true));
      i = j;
      continue;
    }

    // Table: a row followed by a "| --- | --- |" separator. Consume the whole
    // block at once (needs lookahead, hence the index loop).
    if (/\|/.test(line) && i + 1 < lines.length && mdIsTableSep(lines[i + 1])) {
      flushAll();
      const header = mdSplitRow(line);
      const rows = [];
      i += 2; // skip header + separator
      while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim() !== '' && !/^```/.test(lines[i])) {
        rows.push(mdSplitRow(lines[i])); i++;
      }
      i--; // step back so the for-loop's i++ lands on the next unconsumed line
      let table = '<div class="md-table-wrap"><table><thead><tr>' +
        header.map((h) => `<th>${parseInline(h)}</th>`).join('') + '</tr></thead>';
      if (rows.length) {
        table += '<tbody>' + rows.map((r) =>
          '<tr>' + header.map((_, ci) => `<td>${parseInline(r[ci] || '')}</td>`).join('') + '</tr>'
        ).join('') + '</tbody>';
      }
      out.push(table + '</table></div>');
      continue;
    }

    let m;
    // Headings: 1–6 '#'s, space after the hashes optional (some models omit it).
    // Levels 4–6 all render as the smallest heading (h4).
    if ((m = line.match(/^(#{1,6})\s*(.+?)\s*$/))) {
      flushAll();
      const lvl = Math.min(m[1].length, 4);
      out.push(`<h${lvl}>${parseInline(m[2])}</h${lvl}>`);
      continue;
    }
    if (/^\s*(\*\*\*|---|___)\s*$/.test(line)) { flushAll(); out.push('<hr>'); continue; }

    if ((m = line.match(/^>\s?(.*)$/))) { flushPara(); flushList(); quote.push(m[1]); continue; }
    flushQuote();

    // Bullets: -, *, +, or Unicode •/‣/◦.
    if ((m = line.match(/^\s*[-*+•‣◦]\s+(.+)$/))) {
      flushPara();
      if (listType && listType !== 'ul') flushList();
      listType = 'ul'; listItems.push(m[1]); continue;
    }
    if ((m = line.match(/^\s*\d+[.)]\s+(.+)$/))) {
      flushPara();
      if (listType && listType !== 'ol') flushList();
      listType = 'ol'; listItems.push(m[1]); continue;
    }

    // Bold-only line used as a section header (very common in models that don't
    // emit '#' headings), e.g. "**Overview:**". Treated as a heading so it gets
    // heading spacing instead of blank-line drift. Guards: short, and not a
    // full bolded sentence (no mid-text ". ").
    if ((m = line.match(/^\*\*(.+?)\*\*\s*:?\s*$/)) && m[1].length <= 64 && !/[.!?]\s/.test(m[1])) {
      flushAll();
      const colon = /:\s*$/.test(line) ? ':' : '';
      out.push(`<h3>${parseInline(m[1])}${colon}</h3>`);
      continue;
    }

    // Ordinary text — accumulate into the current paragraph.
    if (listType) flushList();
    para.push(line.trim());
  }

  if (inCode && code.length) out.push(renderCode(code.join('\n'), codeLang));
  flushAll();
  return out.join('');
};

// ===== Auto-scroll system =====
let autoScrollEnabled = true;
let lastScrollTop = 0;

const scrollToBottomBtn = document.getElementById("scrollToBottomBtn");

// If user manually scrolls up, pause auto-scroll. Resume when near bottom.
chatWindow.addEventListener("scroll", () => {
  const currentScrollTop = chatWindow.scrollTop;
  const isScrolledUp = currentScrollTop < lastScrollTop;
  lastScrollTop = currentScrollTop;

  let distFromBottom;
  const spacer = chatWindow.querySelector(".scroll-spacer");
  if (spacer) {
    const lastMsg = chatWindow.querySelector(".message:last-of-type");
    if (lastMsg) {
      const winBottom = chatWindow.getBoundingClientRect().bottom;
      const msgBottom = lastMsg.getBoundingClientRect().bottom;
      distFromBottom = msgBottom - winBottom;
    } else {
      distFromBottom = 0;
    }
  } else {
    distFromBottom = chatWindow.scrollHeight - chatWindow.scrollTop - chatWindow.clientHeight;
  }

  if (isScrolledUp) {
    autoScrollEnabled = false;
  } else if (distFromBottom < 15) {
    autoScrollEnabled = true;
  }

  if (chatWindow.classList.contains("is-empty") || chatWindow.scrollHeight <= chatWindow.clientHeight) {
    scrollToBottomBtn.classList.remove("is-visible");
  } else if (distFromBottom > 180) {
    scrollToBottomBtn.classList.add("is-visible");
  } else {
    scrollToBottomBtn.classList.remove("is-visible");
  }
}, { passive: true });

scrollToBottomBtn.addEventListener("click", () => {
  autoScrollEnabled = false;
  scrollToBottom(true);

  // Wait for the smooth scroll to finish before re-enabling 
  // the instant typeWriter cursor tracker, so it doesn't cancel the scroll animation.
  setTimeout(() => {
    autoScrollEnabled = true;
  }, 450);
});

const scrollToBottom = (smooth = false) => {
  const spacer = chatWindow.querySelector(".scroll-spacer");
  if (spacer) {
    // During generation, scroll to the last message, not the spacer
    const lastMsg = chatWindow.querySelector(".message:last-of-type");
    if (lastMsg) {
      const winTop = chatWindow.getBoundingClientRect().top;
      const msgBottom = lastMsg.getBoundingClientRect().bottom;
      const offset = msgBottom - winTop - chatWindow.clientHeight + 24;
      chatWindow.scrollBy({ top: offset, behavior: smooth ? "smooth" : "instant" });
      return;
    }
  }
  chatWindow.scrollTo({
    top: chatWindow.scrollHeight,
    behavior: smooth ? "smooth" : "instant"
  });
};

// Scroll new user message to the top of the chat viewport
const scrollMessageToTop = (messageEl) => {
  // Temporarily clear animations so we read true layout coordinates, not in-progress animation offsets
  const prevAnim = messageEl.style.animation;
  const prevTransform = messageEl.style.transform;
  messageEl.style.animation = "none";
  messageEl.style.transform = "none";

  const windowTop = chatWindow.getBoundingClientRect().top;
  const msgTop = messageEl.getBoundingClientRect().top;
  const offset = msgTop - windowTop;

  chatWindow.scrollBy({
    top: offset - 32, // 32px padding to perfectly match the chat window's top padding for 1:1 symmetry across all bubbles
    behavior: "smooth"
  });

  // Restore animations seamlessly
  messageEl.style.animation = prevAnim;
  messageEl.style.transform = prevTransform;
};

const typeWriterEffect = async (element, text, speed = 20) => {
  element.innerHTML = "";
  const tokens = text.split(/(\s+)/);
  let accumulated = "";

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    // Stop typing if the generation was aborted
    if (!isSending) break;
    if (token === "") continue;

    accumulated += token;
    element.innerHTML = parseMarkdown(accumulated);

    // Auto-scroll to follow the cursor while typing
    if (autoScrollEnabled) {
      const elementRect = element.getBoundingClientRect();
      const windowRect = chatWindow.getBoundingClientRect();
      if (elementRect.bottom > windowRect.bottom - 24) {
        chatWindow.scrollTop += (elementRect.bottom - windowRect.bottom + 24);
      }
    }

    // Small pause only for visible words, not whitespace
    if (token.trim().length > 0) {
      await new Promise((resolve) => setTimeout(resolve, speed));
    }
  }
};

// The composer box is a <div> (not a <label>), so clicking its empty areas
// won't focus the textarea for free — wire that up for parity.
const composerBoxEl = document.querySelector(".composer-box");
if (composerBoxEl) {
  composerBoxEl.addEventListener("mousedown", (e) => {
    if (e.target === composerBoxEl || e.target.classList.contains("composer-main")) {
      e.preventDefault();
      promptInput.focus();
    }
  });
}

// Attachment logic
if (attachmentTrigger) {
  attachmentTrigger.addEventListener("click", () => {
    const isOpening = attachmentMenu.hidden;
    attachmentMenu.hidden = !isOpening;
    attachmentTrigger.classList.toggle("is-open", isOpening);
    attachmentTrigger.setAttribute("aria-expanded", String(isOpening));
  });
}

if (uploadDocBtn) {
  uploadDocBtn.addEventListener("click", () => {
    docInput.click();
    attachmentMenu.hidden = true;
    attachmentTrigger.classList.remove("is-open");
  });
}

let stagedFile = null;

if (docInput) {
  docInput.addEventListener("change", async () => {
    const file = docInput.files[0];
    if (!file) return;

    const allowedExtensions = [".pdf", ".docx", ".txt", ".xlsx"];
    const fileName = file.name.toLowerCase();
    const hasAllowedExt = allowedExtensions.some(ext => fileName.endsWith(ext));

    if (!hasAllowedExt) {
      alert("Please upload a supported file type (.pdf, .docx, .txt, .xlsx).");
      return;
    }

    // UX-only size check — the server independently enforces the same
    // limit while streaming (SEC-09).
    const MAX_UPLOAD_MB = 20;
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      alert(`File is too large. Maximum size is ${MAX_UPLOAD_MB} MB.`);
      docInput.value = "";
      return;
    }

    stagedFile = file;

    // Show chip in composer without spinner
    composerAttachments.hidden = false;
    composerAttachments.innerHTML = "";
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    chip.innerHTML = `
      <span class="attachment-chip-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 14px; height: 14px;">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
      </span>
      <span class="attachment-chip-name">${escapeHtml(file.name)}</span>
      <button type="button" class="attachment-chip-remove" style="background:none; border:none; color:inherit; cursor:pointer; padding:0 4px; font-size:16px;">&times;</button>
    `;
    
    chip.querySelector(".attachment-chip-remove").addEventListener("click", () => {
      stagedFile = null;
      docInput.value = "";
      composerAttachments.innerHTML = "";
      composerAttachments.hidden = true;
    });

    composerAttachments.appendChild(chip);
  });
}


const showConfirmDialog = (title, description, confirmText = "Confirm") => {
  return new Promise((resolve) => {
    confirmTitle.textContent = title;
    confirmDescription.textContent = description;
    confirmBtn.textContent = confirmText;
    confirmOverlay.classList.add("is-open");

    const cleanup = (result) => {
      confirmOverlay.classList.remove("is-open");
      confirmBtn.removeEventListener("click", onConfirm);
      confirmCancelBtn.removeEventListener("click", onCancel);
      confirmOverlay.removeEventListener("click", onOverlayClick);
      resolve(result);
    };

    const onConfirm = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onOverlayClick = (e) => {
      if (e.target === confirmOverlay) cleanup(false);
    };

    confirmBtn.addEventListener("click", onConfirm);
    confirmCancelBtn.addEventListener("click", onCancel);
    confirmOverlay.addEventListener("click", onOverlayClick);
  });
};

const showPromptDialog = (title, defaultValue = "", confirmText = "Save") => {
  return new Promise((resolve) => {
    promptTitle.textContent = title;
    promptInputBox.value = defaultValue;
    promptBtn.textContent = confirmText;
    promptOverlay.classList.add("is-open");
    promptInputBox.focus();

    const cleanup = (result) => {
      promptOverlay.classList.remove("is-open");
      promptBtn.removeEventListener("click", onConfirm);
      promptCancelBtn.removeEventListener("click", onCancel);
      promptOverlay.removeEventListener("click", onOverlayClick);
      promptInputBox.removeEventListener("keydown", onKeyDown);
      resolve(result);
    };

    const onConfirm = () => cleanup(promptInputBox.value);
    const onCancel = () => cleanup(null);
    const onOverlayClick = (e) => {
      if (e.target === promptOverlay) cleanup(null);
    };
    const onKeyDown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      }
    };

    promptBtn.addEventListener("click", onConfirm);
    promptCancelBtn.addEventListener("click", onCancel);
    promptOverlay.addEventListener("click", onOverlayClick);
    promptInputBox.addEventListener("keydown", onKeyDown);
  });
};

composer.addEventListener("submit", (event) => {
  event.preventDefault();

  if (isSending) {
    return;
  }

  const value = promptInput.value.trim();
  if (!value && !stagedFile) {
    return;
  }

  // Deep Research and Document each run their own multi-step workspace flow
  // instead of the standard single-bubble /api/chat path.
  if ((activeMode === DEEP_MODE || activeMode === DOC_MODE) && value) {
    if (stagedFile) {
      stagedFile = null;
      docInput.value = "";
      if (composerAttachments) {
        composerAttachments.innerHTML = "";
        composerAttachments.hidden = true;
      }
    }
    promptInput.value = "";
    autoResize();
    if (activeMode === DEEP_MODE) handleDeepResearchSubmit(value);
    else handleDocumentSubmit(value);
    return;
  }

  // Capture the file to upload and immediately clear the UI
  const fileToUpload = stagedFile;
  stagedFile = null;
  docInput.value = "";
  if (composerAttachments) {
    composerAttachments.innerHTML = "";
    composerAttachments.hidden = true;
  }

  const wasEmpty = chatWindow.querySelector(".message") === null;
  const composerRect = composer.getBoundingClientRect();
  const introRect = wasEmpty ? chatIntro.getBoundingClientRect() : null;
  
  let fileMsg = null;
  let userMessage = null;
  let compositeMsg = null;

  if (fileToUpload && value) {
    compositeMsg = document.createElement("article");
    compositeMsg.className = "message user animate-in";

    const groupContainer = document.createElement("div");
    groupContainer.className = "message-group";
    groupContainer.style.display = "flex";
    groupContainer.style.flexDirection = "column";
    groupContainer.style.alignItems = "stretch"; // Forces both to have same width
    groupContainer.style.gap = "0";

    const fileCardContainer = document.createElement("div");
    fileCardContainer.className = "message-card file-card-wrapper";
    fileCardContainer.style.padding = "0";
    fileCardContainer.style.background = "transparent";
    fileCardContainer.style.boxShadow = "none";
    fileCardContainer.style.border = "none";

    const fileName = fileToUpload.name;
    fileCardContainer.innerHTML = `<div class="file-attachment-card is-uploading" style="margin: 0; width: 100%; box-sizing: border-box; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px;">
          <div class="file-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
          <div class="file-info">
            <span class="file-name" style="color: var(--text);">${escapeHtml(fileName)}</span>
            <span class="file-meta">Indexing document...</span>
          </div>
          <div class="file-status-icon">
            <div class="spinner-mini" style="width: 16px; height: 16px; border-width: 2px;"></div>
          </div>
        </div>`;
    groupContainer.append(fileCardContainer);
    fileMsg = compositeMsg; // Upload logic uses fileMsg.querySelector

    const textCardContainer = document.createElement("div");
    textCardContainer.className = "message-card";
    textCardContainer.style.borderTopLeftRadius = "6px";
    textCardContainer.style.borderTopRightRadius = "6px";
    textCardContainer.style.marginTop = "4px"; // Tiny separator line
    textCardContainer.innerHTML = `<div class="message-text">${escapeHtml(value)}</div>`;
    groupContainer.append(textCardContainer);

    compositeMsg.append(groupContainer);
    appendUserFooter(compositeMsg);
    chatWindow.append(compositeMsg);
    
    // Assign userMessage for scrolling
    userMessage = compositeMsg;
  } else {
    // Standard un-joined rendering for single items
    if (fileToUpload) {
      fileMsg = createMessage("user", `Uploaded file: ${fileToUpload.name}`, { fileStatus: "pending" });
      chatWindow.append(fileMsg);
      userMessage = fileMsg;
    }
    
    if (value) {
      userMessage = createMessage("user", value);
      chatWindow.append(userMessage);
    }
  }

  const pendingMessage = createMessage("assistant", "", { pending: true });
  chatWindow.append(pendingMessage);

  // Temporary spacer to guarantee enough scroll room for the user bubble to reach the top
  const scrollSpacer = document.createElement("div");
  scrollSpacer.className = "scroll-spacer";
  scrollSpacer.style.height = chatWindow.clientHeight + "px";
  scrollSpacer.style.pointerEvents = "none";
  chatWindow.append(scrollSpacer);

  syncStageState();

  if (wasEmpty) {
    animateLayoutShift(chatIntro, introRect, 420);
    animateLayoutShift(composer, composerRect, 360);
    chatWindow.classList.remove("is-revealing");
    void chatWindow.offsetWidth;
    chatWindow.classList.add("is-revealing");
    animateLayoutShift(chatWindow, introRect, 360);
    window.setTimeout(() => {
      chatWindow.classList.remove("is-revealing");
    }, 300);
  }

  promptInput.value = "";
  autoResize();
  setComposerBusy(true);

  // Always scroll the user's new message to the top
  // so they can read the full response from the start
  // Double-rAF ensures layout + paint are fully committed before scrolling
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      scrollMessageToTop(userMessage || fileMsg);
      // Re-enable auto-scroll after the smooth scroll animation finishes,
      // so the scroll listener doesn't disable it mid-animation.
      setTimeout(() => {
        autoScrollEnabled = true;
      }, 450);
    });
  });

  activeAbortController = new AbortController();

  // Single cleanup for every exit that abandons the turn before the
  // assistant-reply flow starts, so no branch can forget to reset the
  // composer state (BUG-22)
  const abandonTurn = () => {
    pendingMessage.remove();
    scrollSpacer.remove();
    setComposerBusy(false);
    activeAbortController = null;
  };

  ensureSession().then(async sessionId => {
    // 1. Process upload if there's a staged file
    if (fileToUpload) {
      const formData = new FormData();
      formData.append("file", fileToUpload);
      
      try {
        const uploadRes = await authFetch(`${BASE_URL}/api/rag/upload?conversation_id=${sessionId}`, {
          method: "POST",
          body: formData
        });
        const uploadData = await uploadRes.json();
        
        if (uploadData.success && fileMsg) {
          const cardBody = fileMsg.querySelector(".file-attachment-card");
          if (cardBody) {
            cardBody.classList.remove("is-uploading");
            cardBody.querySelector(".file-meta").textContent = "Document indexed";
            cardBody.querySelector(".file-status-icon").innerHTML = `
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            `;
          }
        } else {
          throw new Error(uploadData.error || "Upload failed");
        }
      } catch (err) {
        if (fileMsg) fileMsg.remove();
        alert(`Upload error: ${err.message}`);
        abandonTurn();

        // Restore text prompt so user doesn't lose their typed message
        if (value) {
          promptInput.value = value;
          autoResize();
        }

        return; // Stop flow completely
      }
    }

    // 2. Process text prompt if present
    if (!value) {
      // If there was ONLY a file and no prompt text, we stop here and remove the pending assistant msg
      abandonTurn();
      return;
    }

    requestAssistantReply(value, sessionId, { signal: activeAbortController.signal })
      .then(async (payload) => {
        if (activeSessionId !== sessionId) return;

        // The router recognised a document request in an ordinary chat turn.
        // Drop the assistant bubble that was waiting for a reply and let the
        // document workspace take the turn from here — the user's message is
        // already on screen and already stored, hence both flags.
        if (payload.route === "document" && payload.brief) {
          pendingMessage.remove();
          scrollSpacer.remove();
          activeAbortController = null;
          if (wasEmpty) fetchConversations();
          await handleDocumentSubmit(payload.brief.topic || value, {
            seededBrief: payload.brief,
            skipUserMessage: true,
            renderUserMessage: false,
            sessionId,
          });
          return;
        }

        const reply = payload.reply;
        const sources = payload.sources || [];
        const model = payload.model || "";

        pendingMessage.classList.remove("is-pending");

        // If it was the first message, refresh sidebar to show the generated title
        if (wasEmpty) {
          fetchConversations();
        }

        await typeWriterEffect(pendingMessage.querySelector(".message-text"), reply);
        // Artifact card goes in after the typewriter finishes so it lands as a
        // completed deliverable rather than appearing mid-stream.
        if (payload.artifact) {
          pendingMessage.querySelector(".message-card")
            .append(buildArtifactCard(payload.artifact));
        }
        appendAssistantFooter(pendingMessage, reply, sources, model);
      })
      .catch((error) => {
        if (activeSessionId !== sessionId) return;

        pendingMessage.classList.remove("is-pending");
        if (error.name === 'AbortError') {
          const abortedMsg = "Response generation stopped.";
          pendingMessage.querySelector(".message-text").textContent = abortedMsg;
          
          // Save the aborted state to the backend
          authFetch(`${BASE_URL}/api/chat/save_aborted`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              conversation_id: sessionId,
              message: abortedMsg
            })
          }).catch(err => console.error("Failed to save aborted state", err));

        } else {
          pendingMessage.classList.add("is-error");
          pendingMessage.querySelector(".message-text").textContent = error.message || "Something went wrong while contacting the backend.";
        }
        setComposerBusy(false);
      })
      .finally(() => {
        if (activeSessionId !== sessionId) return;

        // Remove the scroll spacer before final positioning
        scrollSpacer.remove();
        setComposerBusy(false);
        activeAbortController = null;
        promptInput.focus();
        // Scroll so the response end + footer sits at the bottom of the viewport
        scrollToBottom();
      });
  }).catch((err) => {
    // Unexpected failure before the reply flow took over — reset the
    // composer instead of leaving it stuck busy (BUG-22)
    console.error("Send flow failed:", err);
    abandonTurn();
  });
});


const ensureSession = async () => {
  if (activeSessionId) return activeSessionId;
  try {
    const resp = await authFetch(CONV_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: parseInt(userId) })
    });
    const data = await resp.json();
    if (data.success) {
      activeSessionId = data.conversation_id;
      // fetch list to show the new "New Conversation" in sidebar
      await fetchConversations();
      return activeSessionId;
    }
  } catch (err) {
    console.error("Session creation failed:", err);
  }
  return 1; // last resort fallback
};

stopButton.addEventListener("click", () => {
  if (activeAbortController) {
    activeAbortController.abort();
    setComposerBusy(false);
  }
});

// ===== Conversation History System =====
const historyList = document.getElementById("historyList");
const newChatBtn = document.getElementById("newChatBtn");

// The options menu is position:fixed, so it doesn't move with the list — close
// it if the list scrolls or the window resizes to avoid a stranded menu.
if (historyList) historyList.addEventListener("scroll", closeHistoryMenus, { passive: true });
window.addEventListener("resize", closeHistoryMenus);

const fetchConversations = async () => {
  try {
    const res = await authFetch(`${CONV_API}/${userId}`);
    const data = await res.json();
    if (data.success) {
      renderConversations(data.conversations);
    }
  } catch (err) {
    console.error("Failed to fetch conversations:", err);
  }
};

const PIN_ICON_SVG = `<svg class="pin-indicator" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.59l-3-3.23V6.5l2-1.5V3H6v2l2 1.5v5.68l-3 3.23z"></path></svg>`;

const renderConversations = (conversations) => {
  if (!historyList) return;
  // Close (and un-portal) any open menu before rebuilding rows, so a menu
  // portalled to <body> can't be orphaned when its row is removed.
  closeHistoryMenus();
  historyList.innerHTML = "";

  conversations.forEach((conv) => {
    const row = document.createElement("div");
    row.className = "history-row";
    if (conv.id === activeSessionId) row.classList.add("active");
    if (conv.is_pinned) row.classList.add("is-pinned");

    const pinIndicator = conv.is_pinned ? PIN_ICON_SVG : "";
    const pinLabel = conv.is_pinned ? "Unpin" : "Pin";

    const isNew = conv.title === "New Conversation";
    // Titles are LLM-generated from user prompt text — untrusted, escape (SEC-07).
    const titleContent = isNew
      ? `<span class="title-loader-bar" title="Generating title..."></span>`
      : escapeHtml(conv.title);

    row.innerHTML = `
      <button class="history-topic ${conv.id === activeSessionId ? "selected" : ""}" type="button" data-id="${conv.id}">
        ${pinIndicator}
        <span class="history-title-text">${titleContent}</span>
      </button>
      <div class="history-actions">
        <button class="history-more" type="button" aria-label="Conversation options" aria-haspopup="true" aria-expanded="false">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <circle cx="5" cy="10" r="1.5"></circle>
            <circle cx="10" cy="10" r="1.5"></circle>
            <circle cx="15" cy="10" r="1.5"></circle>
          </svg>
        </button>
        <div class="history-menu" hidden>
          <button type="button" class="history-menu-share">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
            Share
          </button>
          <button type="button" class="history-menu-pin">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.59l-3-3.23V6.5l2-1.5V3H6v2l2 1.5v5.68l-3 3.23z"></path></svg>
            ${pinLabel}
          </button>
          <button type="button" class="history-menu-rename">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            Rename
          </button>
          <button type="button" class="history-menu-delete">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
            Delete
          </button>
        </div>
      </div>
    `;

    const topicBtn = row.querySelector(".history-topic");
    topicBtn.addEventListener("click", () => {
      // Allow background generation. Just reset the composer so user can chat in the new conversation
      if (isSending) {
        setComposerBusy(false);
        activeAbortController = null;
      }
      loadConversation(conv.id);
    });

    // Re-bind more button logic for dynamic elements
    const moreBtn = row.querySelector(".history-more");
    const menu = row.querySelector(".history-menu");
    const pinBtn = menu.querySelector(".history-menu-pin");
    const renameBtn = menu.querySelector(".history-menu-rename");
    const deleteBtn = menu.querySelector(".history-menu-delete");

    moreBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpening = menu.hidden;
      closeHistoryMenus();
      if (isOpening) {
        moreBtn.classList.add("is-open");
        moreBtn.setAttribute("aria-expanded", "true");
        row.style.zIndex = "200";
        openHistoryMenu(moreBtn, menu);
      }
    });

    pinBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeHistoryMenus();
      handleTogglePin(conv.id, conv.is_pinned);
    });

    renameBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeHistoryMenus();
      handleRenameConversation(conv.id, conv.title);
    });

    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeHistoryMenus();
      handleDeleteConversation(conv.id);
    });

    historyList.appendChild(row);
  });
};

const handleTogglePin = async (sessionId, currentlyPinned) => {
  const action = currentlyPinned ? "unpin" : "pin";
  const confirmed = await showConfirmDialog(
    `${currentlyPinned ? "Unpin" : "Pin"} Conversation`,
    `Are you sure you want to ${action} this conversation?`,
    currentlyPinned ? "Unpin" : "Pin"
  );
  if (!confirmed) return;

  try {
    const res = await authFetch(`${CONV_API}/${sessionId}/pin`, {
      method: "POST"
    });
    const data = await res.json();
    if (data.success) {
      fetchConversations();
    }
  } catch (err) {
    console.error("Pin toggle failed:", err);
  }
};

const handleRenameConversation = async (sessionId, currentTitle) => {
  const newTitle = await showPromptDialog("Enter new title:", currentTitle, "Save");
  if (newTitle === null || newTitle.trim() === "" || newTitle === currentTitle) return;

  try {
    const res = await authFetch(`${CONV_API}/${sessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle.trim() })
    });
    const data = await res.json();
    if (data.success) {
      fetchConversations();
    }
  } catch (err) {
    console.error("Rename failed:", err);
  }
};

const handleDeleteConversation = async (sessionId) => {
  const confirmed = await showConfirmDialog(
    "Delete Conversation",
    "Are you sure you want to delete this conversation? This action cannot be undone.",
    "Delete"
  );
  if (!confirmed) return;

  try {
    const res = await authFetch(`${CONV_API}/${sessionId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.success) {
      if (activeSessionId === sessionId) {
        startNewChat();
      }
      fetchConversations();
    }
  } catch (err) {
    console.error("Delete failed:", err);
  }
};


const loadConversation = async (sessionId) => {
  if (activeSessionId === sessionId) return;
  activeSessionId = sessionId;

  // Update selection UI
  const topics = historyList.querySelectorAll(".history-topic");
  topics.forEach(t => {
    t.classList.toggle("selected", parseInt(t.dataset.id) === sessionId);
  });

  chatWindow.innerHTML = "";
  closeReportCanvas(); // the card backing the open report is about to be discarded
  setComposerBusy(true);

  try {
    const res = await authFetch(`${MSG_API}/${sessionId}`);
    const data = await res.json();
    if (data.success) {
      data.messages.forEach(msg => {
        // A persisted deep-research run replays as the two-pane workspace.
        if (msg.role === "assistant" && msg.research_trace) {
          chatWindow.append(replayResearchTrace(
            msg.research_trace, msg.content, msg.sources || [], msg.id ?? null,
          ));
          return;
        }
        // A document run replays as its own card, the same way.
        if (msg.role === "assistant" && msg.doc_trace) {
          chatWindow.append(replayDocumentTrace(
            msg.doc_trace, msg.content, msg.sources || [], msg.id ?? null,
          ));
          return;
        }
        const msgEl = createMessage(msg.role, msg.content, {
          sources: msg.sources || [],
          artifact: msg.artifact || null,
        });
        chatWindow.append(msgEl);
      });
      syncStageState();
      scrollToBottom();
    }
  } catch (err) {
    console.error("Failed to load conversation:", err);
  } finally {
    setComposerBusy(false);
  }
};

const startNewChat = () => {
  if (isSending) {
    setComposerBusy(false);
    activeAbortController = null;
  }
  activeSessionId = null;
  chatWindow.innerHTML = "";
  closeReportCanvas();
  syncStageState();
  const topics = historyList.querySelectorAll(".history-topic");
  topics.forEach(t => t.classList.remove("selected"));
  promptInput.focus();
};

if (newChatBtn) {
  newChatBtn.addEventListener("click", startNewChat);
}

// Initial fetch — skipped in preview mode (file://), where there's no backend
if (IS_SERVED) {
  fetchConversations();
}

setActiveMode(CHAT_MODE);
syncPanelToggles();
autoResize();
initLoadAnimations();

// ===== Account Management Dialog =====
const AUTH_API = "http://127.0.0.1:8000/api/auth";

const accountOverlay = document.getElementById("accountOverlay");
const accountDialogClose = document.getElementById("accountDialogClose");
const manageAccountBtn = document.getElementById("manageAccountBtn");
const profileEditBtn = document.getElementById("profileEditBtn");
const profileActions = document.getElementById("profileActions");
const profileSaveBtn = document.getElementById("profileSaveBtn");
const profileCancelBtn = document.getElementById("profileCancelBtn");
const passwordSaveBtn = document.getElementById("passwordSaveBtn");
const accountDialogStatus = document.getElementById("accountDialogStatus");

const passwordConfirmOverlay = document.getElementById("passwordConfirmOverlay");
const passwordConfirmClose = document.getElementById("passwordConfirmClose");
const confirmEditSaveBtn = document.getElementById("confirmEditSaveBtn");
const confirmEditCancelBtn = document.getElementById("confirmEditCancelBtn");
const passwordConfirmStatus = document.getElementById("passwordConfirmStatus");

const acctFirstName = document.getElementById("acctFirstName");
const acctLastName = document.getElementById("acctLastName");
const acctEmail = document.getElementById("acctEmail");
const acctDobDay = document.getElementById("acctDobDay");
const acctDobYear = document.getElementById("acctDobYear");
const acctDobMonth = document.getElementById("acctDobMonth");
const acctGenderHidden = document.getElementById("acctGender");

const acctDobMonthSelect = document.getElementById("acctDobMonthSelect");
const acctGenderSelect = document.getElementById("acctGenderSelect");

// All custom selects inside account dialog
const acctCustomSelects = document.querySelectorAll(".acct-custom-select");

// Editable simple inputs (not email)
const editableInputFields = [acctFirstName, acctLastName, acctDobDay, acctDobYear];

let originalProfileData = {};

// -- Custom Select Logic for Account Dialog --
acctCustomSelects.forEach(customSelect => {
  const trigger = customSelect.querySelector(".acct-custom-select-trigger");
  const valueSpan = customSelect.querySelector(".acct-custom-select-value");
  const options = customSelect.querySelectorAll(".acct-custom-option");
  const hiddenInput = customSelect.querySelector("input[type='hidden']");

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (customSelect.classList.contains("disabled")) return;
    // Close other open account selects
    acctCustomSelects.forEach(s => {
      if (s !== customSelect) s.classList.remove("open");
    });
    customSelect.classList.toggle("open");
  });

  options.forEach(option => {
    option.addEventListener("click", function (e) {
      e.stopPropagation();
      options.forEach(opt => opt.classList.remove("selected"));
      this.classList.add("selected");
      customSelect.classList.remove("open");
      customSelect.classList.add("selected");
      valueSpan.textContent = this.textContent;
      hiddenInput.value = this.dataset.value;
    });
  });
});

// Close account custom selects when clicking outside
document.addEventListener("click", (e) => {
  if (!e.target.closest(".acct-custom-select")) {
    acctCustomSelects.forEach(s => s.classList.remove("open"));
  }
});

// -- Helper: set custom select value programmatically --
const setAcctCustomSelectValue = (selectEl, value) => {
  const valueSpan = selectEl.querySelector(".acct-custom-select-value");
  const options = selectEl.querySelectorAll(".acct-custom-option");
  const hiddenInput = selectEl.querySelector("input[type='hidden']");
  let found = false;

  options.forEach(opt => {
    opt.classList.remove("selected");
    if (opt.dataset.value === value) {
      opt.classList.add("selected");
      valueSpan.textContent = opt.textContent;
      hiddenInput.value = value;
      selectEl.classList.add("selected");
      found = true;
    }
  });

  if (!found) {
    // Reset to placeholder
    hiddenInput.value = "";
    selectEl.classList.remove("selected");
    if (selectEl === acctDobMonthSelect) valueSpan.textContent = "Month";
    else if (selectEl === acctGenderSelect) valueSpan.textContent = "Select gender";
  }
};

// -- Helper: parse DOB string "YYYY-MM-DD" into parts --
const parseDob = (dob) => {
  if (!dob) return { month: "", day: "", year: "" };
  const parts = dob.split("-");
  return { year: parts[0] || "", month: parts[1] || "", day: parts[2] || "" };
};

// -- Helper: assemble DOB from parts --
const assembleDob = () => {
  const m = acctDobMonth.value;
  let d = acctDobDay.value;
  const y = acctDobYear.value;
  if (d && d.length === 1) d = "0" + d;
  return (m && d && y) ? `${y}-${m}-${d}` : "";
};

// -- Helper: set disabled state for custom selects --
const setCustomSelectsDisabled = (disabled) => {
  acctCustomSelects.forEach(s => {
    if (disabled) {
      s.classList.add("disabled");
      s.classList.remove("open");
    } else {
      s.classList.remove("disabled");
    }
  });
};

// Password visibility toggles
document.querySelectorAll(".acct-pw-toggle").forEach(btn => {
  btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.target);
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    btn.textContent = isPassword ? "Hide" : "Show";
  });
});

const openAccountDialog = async () => {
  closeAccountMenu();
  accountDialogStatus.textContent = "";
  resetProfileEdit();
  clearPasswordFields();

  // Fetch profile from API
  try {
    const res = await authFetch(`${AUTH_API}/profile/${userId}`);
    const data = await res.json();
    if (data.error) {
      accountDialogStatus.textContent = data.error;
      accountDialogStatus.style.color = "#ff8d72";
    } else {
      acctFirstName.value = data.first_name || "";
      acctLastName.value = data.last_name || "";
      acctEmail.value = data.email || "";

      const dob = parseDob(data.dob);
      setAcctCustomSelectValue(acctDobMonthSelect, dob.month);
      acctDobDay.value = dob.day ? parseInt(dob.day, 10) : "";
      acctDobYear.value = dob.year || "";

      setAcctCustomSelectValue(acctGenderSelect, data.gender || "");

      originalProfileData = {
        first_name: data.first_name || "",
        last_name: data.last_name || "",
        dob: data.dob || "",
        gender: data.gender || ""
      };
    }
  } catch {
    accountDialogStatus.textContent = "Failed to load profile.";
    accountDialogStatus.style.color = "#ff8d72";
  }

  accountOverlay.classList.add("is-open");
};

const closeAccountDialog = () => {
  accountOverlay.classList.remove("is-open");
  resetProfileEdit();
};

const resetProfileEdit = () => {
  editableInputFields.forEach(f => f.disabled = true);
  setCustomSelectsDisabled(true);
  profileEditBtn.textContent = "Edit";
  profileActions.hidden = true;
};

const clearPasswordFields = () => {
  document.getElementById("acctCurrentPassword").value = "";
  document.getElementById("acctNewPassword").value = "";
  document.getElementById("acctConfirmPassword").value = "";
  document.querySelectorAll(".acct-pw-toggle").forEach(btn => {
    btn.textContent = "Show";
    const input = document.getElementById(btn.dataset.target);
    if (input) input.type = "password";
  });
};

const setStatus = (el, msg, isError = false) => {
  el.textContent = msg;
  el.style.color = isError ? "#ff8d72" : "var(--lime)";
};

// -- Restore original profile values --
const restoreOriginalProfile = () => {
  acctFirstName.value = originalProfileData.first_name;
  acctLastName.value = originalProfileData.last_name;
  const dob = parseDob(originalProfileData.dob);
  setAcctCustomSelectValue(acctDobMonthSelect, dob.month);
  acctDobDay.value = dob.day ? parseInt(dob.day, 10) : "";
  acctDobYear.value = dob.year || "";
  setAcctCustomSelectValue(acctGenderSelect, originalProfileData.gender);
};

// Open dialog
manageAccountBtn.addEventListener("click", openAccountDialog);

// Close dialog
accountDialogClose.addEventListener("click", closeAccountDialog);
accountOverlay.addEventListener("click", (e) => {
  if (e.target === accountOverlay) closeAccountDialog();
});

// Edit toggle
profileEditBtn.addEventListener("click", () => {
  const isEditing = !acctFirstName.disabled;
  if (isEditing) {
    restoreOriginalProfile();
    resetProfileEdit();
  } else {
    editableInputFields.forEach(f => f.disabled = false);
    setCustomSelectsDisabled(false);
    profileEditBtn.textContent = "Cancel";
    profileActions.hidden = false;
    acctFirstName.focus();
  }
});

// Cancel button in profile actions
profileCancelBtn.addEventListener("click", () => {
  restoreOriginalProfile();
  resetProfileEdit();
  accountDialogStatus.textContent = "";
});

// Save profile → open password confirmation
profileSaveBtn.addEventListener("click", () => {
  accountDialogStatus.textContent = "";
  passwordConfirmStatus.textContent = "";
  document.getElementById("confirmEditPassword").value = "";
  passwordConfirmOverlay.classList.add("is-open");
});

// Close password confirmation
passwordConfirmClose.addEventListener("click", () => {
  passwordConfirmOverlay.classList.remove("is-open");
});
confirmEditCancelBtn.addEventListener("click", () => {
  passwordConfirmOverlay.classList.remove("is-open");
});
passwordConfirmOverlay.addEventListener("click", (e) => {
  if (e.target === passwordConfirmOverlay) passwordConfirmOverlay.classList.remove("is-open");
});

// Confirm & Save profile edits
confirmEditSaveBtn.addEventListener("click", async () => {
  const pw = document.getElementById("confirmEditPassword").value.trim();
  if (!pw) {
    setStatus(passwordConfirmStatus, "Please enter your password.", true);
    return;
  }

  setStatus(passwordConfirmStatus, "Saving...", false);
  passwordConfirmStatus.style.color = "var(--muted)";

  const dob = assembleDob();

  // Reject impossible calendar dates like 2000-02-31 (BUG-27): JS Date
  // silently rolls them over, so verify the components round-trip exactly.
  if (dob) {
    const dobDate = new Date(`${dob}T00:00:00`);
    const isRealDate = !isNaN(dobDate.getTime())
      && dobDate.getFullYear() === Number(acctDobYear.value)
      && dobDate.getMonth() + 1 === Number(acctDobMonth.value)
      && dobDate.getDate() === Number(acctDobDay.value);
    if (!isRealDate || dobDate > new Date()) {
      setStatus(passwordConfirmStatus, "Please enter a valid date of birth (that day does not exist).", true);
      return;
    }
  }

  try {
    const res = await authFetch(`${AUTH_API}/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: parseInt(userId),
        password: pw,
        first_name: acctFirstName.value.trim(),
        last_name: acctLastName.value.trim(),
        dob: dob,
        gender: acctGenderHidden.value
      })
    });
    const data = await res.json();

    if (data.error) {
      setStatus(passwordConfirmStatus, data.error, true);
    } else if (data.success) {
      passwordConfirmOverlay.classList.remove("is-open");
      setStatus(accountDialogStatus, "Profile updated successfully!", false);

      // Update localStorage & sidebar
      if (data.first_name) {
        localStorage.setItem("lovelace_user_name", data.first_name);
        updateUserIdentity(data.first_name);
      }

      originalProfileData = {
        first_name: acctFirstName.value.trim(),
        last_name: acctLastName.value.trim(),
        dob: dob,
        gender: acctGenderHidden.value
      };

      resetProfileEdit();
    }
  } catch {
    setStatus(passwordConfirmStatus, "Network error. Please try again.", true);
  }
});

// Change Password
passwordSaveBtn.addEventListener("click", async () => {
  const currentPw = document.getElementById("acctCurrentPassword").value.trim();
  const newPw = document.getElementById("acctNewPassword").value.trim();
  const confirmPw = document.getElementById("acctConfirmPassword").value.trim();

  if (!currentPw || !newPw || !confirmPw) {
    setStatus(accountDialogStatus, "Please fill in all password fields.", true);
    return;
  }

  if (newPw !== confirmPw) {
    setStatus(accountDialogStatus, "New passwords do not match.", true);
    return;
  }

  if (newPw.length < 6) {
    setStatus(accountDialogStatus, "New password must be at least 6 characters.", true);
    return;
  }

  setStatus(accountDialogStatus, "Updating password...", false);
  accountDialogStatus.style.color = "var(--muted)";

  try {
    const res = await authFetch(`${AUTH_API}/change-password`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: parseInt(userId),
        current_password: currentPw,
        new_password: newPw
      })
    });
    const data = await res.json();

    if (data.error) {
      setStatus(accountDialogStatus, data.error, true);
    } else if (data.success) {
      setStatus(accountDialogStatus, "Password updated successfully! Logging out...", false);
      clearPasswordFields();
      // Token was rotated server-side (SEC-01) — force a fresh login
      localStorage.removeItem("lovelace_user_id");
      localStorage.removeItem("lovelace_user_name");
      localStorage.removeItem("lovelace_token");
      setTimeout(() => {
        window.location.replace("login.html");
      }, 1500);
    }
  } catch {
    setStatus(accountDialogStatus, "Network error. Please try again.", true);
  }
});
