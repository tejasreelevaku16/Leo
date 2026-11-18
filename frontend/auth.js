
const API_URL = "http://127.0.0.1:8000";

const signupForm = document.getElementById("signup-form");
const loginForm = document.getElementById("login-form");

// Check if user already has an active session and redirect to chat
async function checkExistingSession() {
    try {
        const response = await fetch(`${API_URL}/auth/me`, {
            method: "GET",
            credentials: "include"
        });
        if (response.ok) {
            window.location.href = "chat.html";
        }
    } catch (e) {
        // Not authenticated or server offline
    }
}
checkExistingSession();

// SIGNUP
if (signupForm) {
    signupForm.addEventListener("submit", async function (event) {
        event.preventDefault();

        const fullName = document.getElementById("full-name").value.trim();
        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;
        const confirmPassword = document.getElementById("confirm-password").value;
        const authMessage = document.getElementById("auth-message");

        if (password.length < 12) {
            authMessage.className = "auth-message error";
            authMessage.textContent = "Password must be at least 12 characters long.";
            return;
        }

        if (password !== confirmPassword) {
            authMessage.className = "auth-message error";
            authMessage.textContent = "Passwords do not match.";
            return;
        }

        authMessage.className = "auth-message info";
        authMessage.textContent = "Creating your account...";

        try {
            const response = await fetch(`${API_URL}/auth/register`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    full_name: fullName,
                    email: email,
                    password: password
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Registration failed.");
            }

            authMessage.className = "auth-message success";
            authMessage.textContent = "Account created successfully! Redirecting...";

            setTimeout(() => {
                window.location.href = "login.html";
            }, 800);

        } catch (error) {
            authMessage.className = "auth-message error";
            authMessage.textContent = error.message;
        }
    });
}

// LOGIN
if (loginForm) {
    loginForm.addEventListener("submit", async function (event) {
        event.preventDefault();

        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;
        const authMessage = document.getElementById("auth-message");

        authMessage.className = "auth-message info";
        authMessage.textContent = "Logging in...";

        try {
            const response = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                credentials: "include",
                body: JSON.stringify({
                    email: email,
                    password: password
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Login failed.");
            }

            authMessage.className = "auth-message success";
            authMessage.textContent = "Login successful! Redirecting...";

            setTimeout(() => {
                window.location.href = "chat.html";
            }, 500);

        } catch (error) {
            authMessage.className = "auth-message error";
            authMessage.textContent = error.message;
        }
    });
}
