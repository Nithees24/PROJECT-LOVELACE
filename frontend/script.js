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
const agentTrigger = document.getElementById("agentTrigger");
const agentMenu = document.getElementById("agentMenu");
const agentOption = document.querySelector(".agent-option[data-mode]");
const accountPopover = document.getElementById("accountPopover");
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
const API_ENDPOINT = (window.LOVELACE_CONFIG && window.LOVELACE_CONFIG.API_ENDPOINT) || "http://127.0.0.1:8000/api/chat";
const BASE_URL = API_ENDPOINT.replace("/api/chat", "");
const CONV_API = `${BASE_URL}/api/conversations`;
const MSG_API = `${BASE_URL}/api/messages`;

// Check if user is logged in
const userId = localStorage.getItem("lovelace_user_id");
const userName = localStorage.getItem("lovelace_user_name");

if (!userId) {
  window.location.replace("login.html");
}

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
    localStorage.removeItem("lovelace_user_id");
    localStorage.removeItem("lovelace_user_name");
    window.location.replace("login.html");
  });
}

let activeMode = CHAT_MODE;
let isSending = false;
let activeAbortController = null;
let activeSessionId = null;
const conversationHistory = [];
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

  if (role === "assistant") {
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
  article.append(card);

  if (role === "assistant" && !options.pending && !options.error) {
    appendAssistantFooter(article, content);
  }
  if (role === "user") {
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
    <textarea class="edit-textarea">${originalText}</textarea>
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
    const reply = await requestAssistantReply(newText, activeSessionId, { signal: activeAbortController.signal });
    pendingMessage.classList.remove("is-pending");
    await typeWriterEffect(pendingMessage.querySelector(".message-text"), reply);
    appendAssistantFooter(pendingMessage, reply);
    scrollToBottom();
  } catch (error) {
    pendingMessage.classList.remove("is-pending");
    if (error.name !== 'AbortError') {
      pendingMessage.classList.add("is-error");
      pendingMessage.querySelector(".message-text").textContent = error.message || "Regeneration failed.";
    }
  }
};

const appendAssistantFooter = (article, content) => {
  const card = article.querySelector(".message-card");
  if (!card || card.querySelector(".message-footer")) return;

  const footer = document.createElement("div");
  footer.className = "message-footer";
  footer.innerHTML = `
    <div class="message-actions-row">
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
          <p class="model-info">Generated by Lovelace Intelligence (Gemini 3 Flash)</p>
        </div>
      </div>
    </div>
  `;

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
          fetch(`${CONV_API}/${activeSessionId}/rate`, {
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
  const response = await fetch(API_ENDPOINT, {
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

  if (typeof payload.reply !== "string" || !payload.reply.trim()) {
    throw new Error("The backend returned an empty reply.");
  }

  return payload.reply;
};

const updatePromptPlaceholder = () => {
  promptInput.placeholder = activeMode === DEEP_MODE
    ? "Use Lovelace to deep research"
    : "Ask Lovelace";
};

const syncStageState = () => {
  const hasMessages = chatWindow.querySelector(".message") !== null;
  const showChip = activeMode === DEEP_MODE;

  modeChipInline.hidden = !showChip;
  chatWindow.classList.toggle("is-empty", !hasMessages);
  chatIntro.hidden = false;
  chatStage.classList.toggle("is-empty-state", !hasMessages);
};

const updateAgentUI = () => {
  agentOption.dataset.mode = DEEP_MODE;
  agentOption.textContent = "Deep research";
  agentTrigger.classList.toggle("is-active", activeMode === DEEP_MODE);
  syncStageState();
};

const setActiveMode = (mode) => {
  activeMode = mode;
  updatePromptPlaceholder();
  updateAgentUI();
  closeAgentMenu();
};

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

const closeAgentMenu = () => {
  agentMenu.hidden = true;
  agentTrigger.classList.remove("is-open");
  agentTrigger.setAttribute("aria-expanded", "false");
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

const closeHistoryMenus = () => {
  document.querySelectorAll(".history-more").forEach((button) => {
    const menu = button.parentElement.querySelector(".history-menu");
    button.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
    if (menu) {
      menu.hidden = true;
      menu.classList.remove("open-upwards");
      const row = button.closest(".history-row");
      if (row) row.style.zIndex = "";
    }
  });
};

agentTrigger.addEventListener("click", () => {
  const isOpening = agentMenu.hidden;
  agentMenu.hidden = !isOpening;
  agentTrigger.classList.toggle("is-open", isOpening);
  agentTrigger.setAttribute("aria-expanded", String(isOpening));
});

profileMenuButton.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleAccountMenu();
});

leftPanelToggle.addEventListener("click", () => {
  pageShell.classList.toggle("left-collapsed");
  syncPanelToggles();
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
    button.classList.toggle("is-open", isOpening);
    button.setAttribute("aria-expanded", String(isOpening));
    if (isOpening) {
      const rect = button.getBoundingClientRect();
      if (window.innerHeight - rect.bottom < 180) {
        menu.classList.add("open-upwards");
      }
    }
    menu.hidden = !isOpening;
  });
});

agentOption.addEventListener("click", () => {
  setActiveMode(DEEP_MODE);
});

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
  if (!event.target.closest(".agent-selector")) {
    closeAgentMenu();
  }
  if (!event.target.closest(".history-actions")) {
    closeHistoryMenus();
  }
  if (!event.target.closest(".account-popover")) {
    closeAccountMenu();
  }
  if (!event.target.closest(".msg-more-container")) {
    document.querySelectorAll(".msg-more-dropdown").forEach(d => d.hidden = true);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAgentMenu();
    closeHistoryMenus();
    closeAccountMenu();
  }
});

const parseMarkdown = (rawText) => {
  if (!rawText) return "";
  let html = rawText;
  // Use [^\n\r]+ to robustly match until the end of the line, handling \r or \n.
  html = html.replace(/^###\s+([^\n\r]+)/gim, '<h3 style="margin: 0.5em 0;">$1</h3>');
  html = html.replace(/^##\s+([^\n\r]+)/gim, '<h2 style="margin: 0.5em 0;">$1</h2>');
  html = html.replace(/^#\s+([^\n\r]+)/gim, '<h1 style="margin: 0.5em 0;">$1</h1>');
  html = html.replace(/^(\*\*\*|---)[\s]*$/gim, '<hr style="border: 0; border-top: 1px solid var(--line); margin: 1.5em 0;">');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  return html;
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

  if (distFromBottom > 180) {
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
  if (!value) {
    return;
  }

  const wasEmpty = chatWindow.querySelector(".message") === null;
  const composerRect = composer.getBoundingClientRect();
  const introRect = wasEmpty ? chatIntro.getBoundingClientRect() : null;
  const userMessage = createMessage("user", value);
  const pendingMessage = createMessage("assistant", "", { pending: true });

  chatWindow.append(userMessage);
  chatWindow.append(pendingMessage);

  // Temporary spacer to guarantee enough scroll room for the user bubble to reach the top
  const scrollSpacer = document.createElement("div");
  scrollSpacer.className = "scroll-spacer";
  scrollSpacer.style.height = chatWindow.clientHeight + "px";
  scrollSpacer.style.pointerEvents = "none";
  chatWindow.append(scrollSpacer);

  conversationHistory.push({ role: "user", content: value });
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
      scrollMessageToTop(userMessage);
      // Re-enable auto-scroll after the smooth scroll animation finishes,
      // so the scroll listener doesn't disable it mid-animation.
      setTimeout(() => {
        autoScrollEnabled = true;
      }, 450);
    });
  });

  activeAbortController = new AbortController();

  // If no active session, create one first
  const ensureSession = async () => {
    if (activeSessionId) return activeSessionId;
    try {
      const resp = await fetch(CONV_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: parseInt(userId) }),
        signal: activeAbortController.signal
      });
      const data = await resp.json();
      if (data.success) {
        activeSessionId = data.conversation_id;
        // fetch list to show the new "New Conversation" in sidebar
        await fetchConversations();
        return activeSessionId;
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Session creation aborted');
      } else {
        console.error("Session creation failed:", err);
      }
    }
    return 1; // last resort fallback
  };

  ensureSession().then(sessionId => {
    requestAssistantReply(value, sessionId, { signal: activeAbortController.signal })
      .then(async (reply) => {
        pendingMessage.classList.remove("is-pending");
        conversationHistory.push({ role: "assistant", content: reply });

        // If it was the first message, refresh sidebar to show the generated title
        if (wasEmpty) {
          fetchConversations();
        }

        await typeWriterEffect(pendingMessage.querySelector(".message-text"), reply);
        appendAssistantFooter(pendingMessage, reply);
      })
      .catch((error) => {
        pendingMessage.classList.remove("is-pending");
        if (error.name === 'AbortError') {
          pendingMessage.querySelector(".message-text").textContent = "Response generation stopped.";
        } else {
          pendingMessage.classList.add("is-error");
          pendingMessage.querySelector(".message-text").textContent = error.message || "Something went wrong while contacting the backend.";
        }
      })
      .finally(() => {
        // Remove the scroll spacer before final positioning
        scrollSpacer.remove();
        setComposerBusy(false);
        activeAbortController = null;
        promptInput.focus();
        // Scroll so the response end + footer sits at the bottom of the viewport
        scrollToBottom();
      });
  });
});

stopButton.addEventListener("click", () => {
  if (activeAbortController) {
    activeAbortController.abort();
    setComposerBusy(false);
  }
});

// ===== Conversation History System =====
const historyList = document.getElementById("historyList");
const newChatBtn = document.getElementById("newChatBtn");

const fetchConversations = async () => {
  try {
    const res = await fetch(`${CONV_API}/${userId}`);
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
  historyList.innerHTML = "";

  conversations.forEach((conv) => {
    const row = document.createElement("div");
    row.className = "history-row";
    if (conv.id === activeSessionId) row.classList.add("active");
    if (conv.is_pinned) row.classList.add("is-pinned");

    const pinIndicator = conv.is_pinned ? PIN_ICON_SVG : "";
    const pinLabel = conv.is_pinned ? "Unpin" : "Pin";

    row.innerHTML = `
      <button class="history-topic ${conv.id === activeSessionId ? "selected" : ""}" type="button" data-id="${conv.id}">
        ${pinIndicator}
        <span class="history-title-text">${conv.title}</span>
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
      if (isSending) return;
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
      moreBtn.classList.toggle("is-open", isOpening);
      moreBtn.setAttribute("aria-expanded", String(isOpening));
      if (isOpening) {
        const rect = moreBtn.getBoundingClientRect();
        if (window.innerHeight - rect.bottom < 180) {
          menu.classList.add("open-upwards");
        }
        row.style.zIndex = "200";
      }
      menu.hidden = !isOpening;
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
    const res = await fetch(`${CONV_API}/${sessionId}/pin`, {
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
    const res = await fetch(`${CONV_API}/${sessionId}`, {
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
    const res = await fetch(`${CONV_API}/${sessionId}`, {
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
  setComposerBusy(true);

  try {
    const res = await fetch(`${MSG_API}/${sessionId}`);
    const data = await res.json();
    if (data.success) {
      data.messages.forEach(msg => {
        const msgEl = createMessage(msg.role, msg.content);
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
  if (isSending) return;
  activeSessionId = null;
  chatWindow.innerHTML = "";
  syncStageState();
  const topics = historyList.querySelectorAll(".history-topic");
  topics.forEach(t => t.classList.remove("selected"));
  promptInput.focus();
};

if (newChatBtn) {
  newChatBtn.addEventListener("click", startNewChat);
}

// Initial fetch
fetchConversations();

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
    const res = await fetch(`${AUTH_API}/profile/${userId}`);
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

  try {
    const res = await fetch(`${AUTH_API}/profile`, {
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
    const res = await fetch(`${AUTH_API}/change-password`, {
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
      setStatus(accountDialogStatus, "Password updated successfully!", false);
      clearPasswordFields();
    }
  } catch {
    setStatus(accountDialogStatus, "Network error. Please try again.", true);
  }
});
