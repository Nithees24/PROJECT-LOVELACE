const pageShell = document.getElementById("pageShell");
const leftPanelToggle = document.getElementById("leftPanelToggle");
const rightPanelToggle = document.getElementById("rightPanelToggle");
const chatWindow = document.getElementById("chatWindow");
const chatStage = document.getElementById("chatStage");
const chatIntro = document.getElementById("chatIntro");
const modeChipInline = document.getElementById("modeChipInline");
const modeChipClose = document.getElementById("modeChipClose");
const composer = document.getElementById("composer");
const promptInput = document.getElementById("promptInput");
const themeToggleCheckbox = document.getElementById("themeToggleCheckbox");
const sendButton = composer.querySelector(".send-button");
const agentTrigger = document.getElementById("agentTrigger");
const agentMenu = document.getElementById("agentMenu");
const agentOption = document.querySelector(".agent-option[data-mode]");
const historyItems = Array.from(document.querySelectorAll(".history-topic"));
const historyMoreButtons = Array.from(document.querySelectorAll(".history-more"));

const CHAT_MODE = "Chat Agent";
const DEEP_MODE = "Deep Research";
const API_ENDPOINT = "http://127.0.0.1:8000/api/chat";

let activeMode = CHAT_MODE;
let isSending = false;
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

const createPanelIcon = (side, collapsed) => {
  if (side === "left") {
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
  }

  return collapsed
    ? `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2"></rect>
        <path d="M15 5v14"></path>
        <path d="M19 12h-2"></path>
      </svg>
    `
    : `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2"></rect>
        <path d="M15 5v14"></path>
        <path d="M17 12h2"></path>
      </svg>
    `;
};

const autoResize = () => {
  promptInput.style.height = "auto";
  promptInput.style.height = `${promptInput.scrollHeight}px`;
};

const initLoadAnimations = () => {
  const revealTargets = [
    ...document.querySelectorAll(".sidebar .panel-body > *"),
    ...document.querySelectorAll(".chat-stage > .panel-controls, .chat-stage > .chat-intro, .chat-stage > .chat-window, .chat-stage > .composer, .chat-stage > .composer-note"),
    ...document.querySelectorAll(".control-panel .panel-body > *")
  ];

  revealTargets.forEach((element, index) => {
    element.classList.add("reveal-on-load");
    element.style.setProperty("--reveal-order", index);
  });

  window.requestAnimationFrame(() => {
    document.body.classList.add("is-loaded");
  });
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
  body.textContent = content;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = LOVELACE_LOGO_SVG;
    article.append(avatar);
  }

  card.append(body);
  article.append(card);
  return article;
};

const setComposerBusy = (busy) => {
  isSending = busy;
  promptInput.disabled = busy;
  sendButton.disabled = busy;
  composer.classList.toggle("is-busy", busy);
};

const requestAssistantReply = async (message) => {
  const response = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message,
      mode: activeMode,
      conversation_id: 1
    })
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
  const rightCollapsed = pageShell.classList.contains("right-collapsed");

  leftPanelToggle.classList.toggle("is-collapsed", leftCollapsed);
  rightPanelToggle.classList.toggle("is-collapsed", rightCollapsed);

  leftPanelToggle.setAttribute("aria-label", leftCollapsed ? "Show left panel" : "Hide left panel");
  leftPanelToggle.setAttribute("title", leftCollapsed ? "Show left panel" : "Hide left panel");
  rightPanelToggle.setAttribute("aria-label", rightCollapsed ? "Show right panel" : "Hide right panel");
  rightPanelToggle.setAttribute("title", rightCollapsed ? "Show right panel" : "Hide right panel");

  leftPanelToggle.innerHTML = createPanelIcon("left", leftCollapsed);
  rightPanelToggle.innerHTML = createPanelIcon("right", rightCollapsed);
};

const closeAgentMenu = () => {
  agentMenu.hidden = true;
  agentTrigger.classList.remove("is-open");
  agentTrigger.setAttribute("aria-expanded", "false");
};

const closeHistoryMenus = () => {
  historyMoreButtons.forEach((button) => {
    const menu = button.parentElement.querySelector(".history-menu");
    button.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
    if (menu) {
      menu.hidden = true;
    }
  });
};

agentTrigger.addEventListener("click", () => {
  const isOpening = agentMenu.hidden;
  agentMenu.hidden = !isOpening;
  agentTrigger.classList.toggle("is-open", isOpening);
  agentTrigger.setAttribute("aria-expanded", String(isOpening));
});

leftPanelToggle.addEventListener("click", () => {
  pageShell.classList.toggle("left-collapsed");
  syncPanelToggles();
});

rightPanelToggle.addEventListener("click", () => {
  pageShell.classList.toggle("right-collapsed");
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
});

const parseMarkdown = (rawText) => {
  let html = rawText;
  html = html.replace(/^### (.*$)/gim, '<h3 style="margin: 0.5em 0;">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 style="margin: 0.5em 0;">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 style="margin: 0.5em 0;">$1</h1>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  return html;
};

const typeWriterEffect = async (element, text, speed = 40) => {
  element.innerHTML = "";
  let accumulatedText = "";
  const words = text.split(/(\s+)/);
  for (let i = 0; i < words.length; i++) {
    accumulatedText += words[i];
    element.innerHTML = parseMarkdown(accumulatedText);
    
    if (words[i].trim().length > 0) {
      await new Promise((resolve) => setTimeout(resolve, speed));
    }
  }
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
  const pendingMessage = createMessage("assistant", "Lovelace is thinking...", { pending: true });

  chatWindow.append(userMessage);
  chatWindow.append(pendingMessage);
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

  chatWindow.scrollTop = chatWindow.scrollHeight;

  promptInput.value = "";
  autoResize();
  setComposerBusy(true);

  requestAssistantReply(value)
    .then(async (reply) => {
      pendingMessage.classList.remove("is-pending");
      conversationHistory.push({ role: "assistant", content: reply });
      await typeWriterEffect(pendingMessage.querySelector(".message-text"), reply);
    })
    .catch((error) => {
      pendingMessage.classList.remove("is-pending");
      pendingMessage.classList.add("is-error");
      pendingMessage.querySelector(".message-text").textContent = error.message || "Something went wrong while contacting the backend.";
    })
    .finally(() => {
      setComposerBusy(false);
      promptInput.focus();
    });
});

setActiveMode(CHAT_MODE);
syncPanelToggles();
autoResize();
initLoadAnimations();
