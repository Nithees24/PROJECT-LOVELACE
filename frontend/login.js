const root = document.documentElement;
const themeToggleCheckbox = document.getElementById("themeToggleCheckbox");
const authPanel = document.getElementById("authPanel");
const statusMessage = document.getElementById("statusMessage");

// Forms
const identifierForm = document.getElementById("identifierForm");
const loginForm = document.getElementById("loginForm");
const signupForm = document.getElementById("signupForm");

// Inputs
const idEmailInput = document.getElementById("idEmailInput");
const passwordInput = document.getElementById("passwordInput");
const passwordToggle = document.getElementById("passwordToggle");

const signupPasswordInput = document.getElementById("signupPasswordInput");
const signupPasswordToggle = document.getElementById("signupPasswordToggle");
const signupConfirmPasswordInput = document.getElementById("signupConfirmPasswordInput");
const signupConfirmPasswordToggle = document.getElementById("signupConfirmPasswordToggle");

// Display Elements
const displayEmails = document.querySelectorAll(".display-email");
const backButtons = document.querySelectorAll("[data-back]");

const THEME_KEY = "lovelace-login-theme";

const applyTheme = (theme) => {
  root.setAttribute("data-theme", theme);
  window.localStorage.setItem(THEME_KEY, theme);
};

const savedTheme = window.localStorage.getItem(THEME_KEY);
if (savedTheme === "light" || savedTheme === "dark") {
  applyTheme(savedTheme);
  if (themeToggleCheckbox) {
    themeToggleCheckbox.checked = savedTheme === "dark";
  }
}

// Theme Toggle
themeToggleCheckbox.addEventListener("change", (e) => {
  const isDark = e.target.checked;
  const theme = isDark ? "dark" : "light";
  
  if (!document.startViewTransition) {
    applyTheme(theme);
    return;
  }

  const rect = e.target.closest('.theme-switch').getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y)
  );

  document.documentElement.classList.add("theme-transition");
  const transition = document.startViewTransition(() => {
    applyTheme(theme);
  });

  transition.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${endRadius}px at ${x}px ${y}px)`] },
      { duration: 500, easing: "ease-out", pseudoElement: "::view-transition-new(root)" }
    );
  });

  transition.finished.then(() => {
    document.documentElement.classList.remove("theme-transition");
  });
});

// Navigation Functions
function setStep(step) {
  authPanel.className = `auth-panel reveal step-${step}`;
  statusMessage.textContent = "";
}

backButtons.forEach(btn => {
  btn.addEventListener("click", () => setStep(1));
});

// Password Toggle shared logic
const setupPasswordToggle = (input, button) => {
  button.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Hide" : "Show";
  });
};

setupPasswordToggle(passwordInput, passwordToggle);
setupPasswordToggle(signupPasswordInput, signupPasswordToggle);
setupPasswordToggle(signupConfirmPasswordInput, signupConfirmPasswordToggle);

// Base API URL (Assuming API runs on same host or define specifically)
const API_BASE = "http://127.0.0.1:8000/api/auth";

// Step 1: Identifier
identifierForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = idEmailInput.value.trim();
  if (!email) return;

  statusMessage.textContent = "Checking details...";
  statusMessage.style.color = "var(--text)";

  try {
    const res = await fetch(`${API_BASE}/check-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email })
    });
    
    if (!res.ok) throw new Error("API completely failed");
    
    const data = await res.json();
    if (data.error) {
       throw new Error(data.error);
    }

    displayEmails.forEach(el => el.textContent = email);

    if (data.exists) {
      setStep(2); // Go to login
    } else {
      setStep(3); // Go to signup
    }
  } catch (err) {
    statusMessage.textContent = err.message || "Failed to reach server.";
    statusMessage.style.color = "#ff8d72";
  }
});

// Step 2: Login
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = idEmailInput.value.trim();
  const password = passwordInput.value.trim();

  statusMessage.textContent = "Authenticating...";
  statusMessage.style.color = "var(--text)";

  try {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();

    if (data.error) {
      statusMessage.textContent = data.error;
      statusMessage.style.color = "#ff8d72";
    } else if (data.success) {
      statusMessage.textContent = `Welcome back, ${data.first_name || 'Researcher'}!`;
      statusMessage.style.color = "var(--accent-2)";
      setTimeout(() => window.location.href = "lovelace.html", 1000);
    }
  } catch (err) {
    statusMessage.textContent = "Error authenticating.";
    statusMessage.style.color = "#ff8d72";
  }
});

// Step 3: Signup
signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = idEmailInput.value.trim();
  const first_name = document.getElementById("firstNameInput").value.trim();
  const last_name = document.getElementById("lastNameInput").value.trim();
  const password = signupPasswordInput.value.trim();
  const confirmPassword = signupConfirmPasswordInput.value.trim();
  const role = document.getElementById("roleInput").value;

  if (password !== confirmPassword) {
    statusMessage.textContent = "Passwords do not match.";
    statusMessage.style.color = "#ff8d72";
    return;
  }

  statusMessage.textContent = "Creating your account...";
  statusMessage.style.color = "var(--text)";

  try {
    const res = await fetch(`${API_BASE}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, first_name, last_name, password, role })
    });
    const data = await res.json();

    if (data.error) {
      statusMessage.textContent = data.error;
      statusMessage.style.color = "#ff8d72";
    } else if (data.success) {
      statusMessage.textContent = "Account created! Routing to workspace...";
      statusMessage.style.color = "var(--accent-2)";
      setTimeout(() => window.location.href = "lovelace.html", 1000);
    }
  } catch (err) {
    statusMessage.textContent = "Error creating account.";
    statusMessage.style.color = "#ff8d72";
  }
});
