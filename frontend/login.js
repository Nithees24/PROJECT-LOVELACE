const root = document.documentElement;
const themeToggleCheckbox = document.getElementById("themeToggleCheckbox");
const authPanel = document.getElementById("authPanel");
const statusMessage = document.getElementById("statusMessage");

// Forms
const identifierForm = document.getElementById("identifierForm");
const loginForm = document.getElementById("loginForm");
const signupNameForm = document.getElementById("signupNameForm");
const signupPasswordForm = document.getElementById("signupPasswordForm");
const signupDetailsForm = document.getElementById("signupDetailsForm");

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

// Base API URL (Use configuration from window if available)
const API_BASE = (window.LOVELACE_CONFIG && window.LOVELACE_CONFIG.API_BASE) || "http://127.0.0.1:8000/api/auth";

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
      
      // Save user info for the workspace
      localStorage.setItem("lovelace_user_id", data.user_id);
      localStorage.setItem("lovelace_user_name", data.first_name);
      
      setTimeout(() => window.location.href = "lovelace.html", 1000);
    }
  } catch (err) {
    statusMessage.textContent = "Error authenticating.";
    statusMessage.style.color = "#ff8d72";
  }
});

// Step 3: Signup Name
signupNameForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const first_name = document.getElementById("firstNameInput").value.trim();
  const last_name = document.getElementById("lastNameInput").value.trim();

  if (!first_name || !last_name) return;
  setStep(4);
});

// Step 4: Signup Password
signupPasswordForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const password = signupPasswordInput.value.trim();
  const confirmPassword = signupConfirmPasswordInput.value.trim();

  if (password !== confirmPassword) {
    statusMessage.textContent = "Passwords do not match.";
    statusMessage.style.color = "#ff8d72";
    return;
  }
  
  if (password.length < 6) {
    statusMessage.textContent = "Password must be at least 6 characters.";
    statusMessage.style.color = "#ff8d72";
    return;
  }

  statusMessage.textContent = "";
  setStep(5);
});

// Step 5: Signup Details and Submit
signupDetailsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = idEmailInput.value.trim();
  const first_name = document.getElementById("firstNameInput").value.trim();
  const last_name = document.getElementById("lastNameInput").value.trim();
  const password = signupPasswordInput.value.trim();
  const role = document.getElementById("roleInput").value;
  const gender = document.getElementById("genderInput").value;
  
  const m = document.getElementById("dobMonthInput").value;
  let d = document.getElementById("dobDayInput").value;
  const y = document.getElementById("dobYearInput").value;
  
  if (d && d.length === 1) d = "0" + d; // prefix padding
  const dob = (m && d && y) ? `${y}-${m}-${d}` : "";

  if (!role) {
    statusMessage.textContent = "Please select a role.";
    statusMessage.style.color = "#ff8d72";
    return;
  }
  if (!dob) {
    statusMessage.textContent = "Please provide your Date of Birth.";
    statusMessage.style.color = "#ff8d72";
    return;
  }
  if (!gender) {
    statusMessage.textContent = "Please select your gender.";
    statusMessage.style.color = "#ff8d72";
    return;
  }

  statusMessage.textContent = "Creating your account...";
  statusMessage.style.color = "var(--text)";

  try {
    const res = await fetch(`${API_BASE}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, first_name, last_name, password, role, dob, gender })
    });
    const data = await res.json();

    if (data.error) {
      document.getElementById("errorDetailMsg").textContent = data.error;
      setStep(7);
    } else if (data.success) {
      statusMessage.textContent = "";
      setStep(6);
      setTimeout(() => setStep(2), 2500); // Go to login after showing success for 2.5s
    }
  } catch (err) {
    document.getElementById("errorDetailMsg").textContent = "We encountered a technical error. Please check your connection.";
    setStep(7);
  }
});

// Custom Select Logic (Universal for multiple select menus)
const customSelects = document.querySelectorAll(".custom-select");

customSelects.forEach(customSelect => {
  const selectTrigger = customSelect.querySelector(".custom-select-trigger");
  const selectValue = customSelect.querySelector(".custom-select-value");
  const options = customSelect.querySelectorAll(".custom-option");
  const hiddenInput = customSelect.querySelector("input[type='hidden']");

  selectTrigger.addEventListener("click", (e) => {
    e.stopPropagation();
    // Close other open selects before opening this one
    customSelects.forEach(s => {
      if (s !== customSelect) s.classList.remove("open");
    });
    customSelect.classList.toggle("open");
  });

  options.forEach(option => {
    option.addEventListener("click", function(e) {
      e.stopPropagation();
      options.forEach(opt => opt.classList.remove("selected"));
      this.classList.add("selected");
      customSelect.classList.remove("open");
      customSelect.classList.add("selected");
      selectValue.textContent = this.textContent;
      hiddenInput.value = this.dataset.value;
    });
  });
});

document.addEventListener("click", (e) => {
  if (!e.target.closest('.custom-select')) {
    customSelects.forEach(s => s.classList.remove("open"));
  }
});
