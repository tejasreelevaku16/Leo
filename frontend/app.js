
const API_URL = "http://127.0.0.1:8000";

const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatMessages = document.getElementById("chat-messages");
const sendButton = document.getElementById("send-button");
const newChatButton = document.getElementById("new-chat");
const searchToggle = document.getElementById("search-toggle");
const conversationList = document.getElementById("conversation-list");
const userDisplay = document.getElementById("user-display");
const logoutBtn = document.getElementById("logout-btn");
const statusText = document.getElementById("status-text");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");

// Profile modal elements
const userProfileBtn = document.getElementById("user-profile-btn");
const profileModal = document.getElementById("profile-modal");
const closeProfileModal = document.getElementById("close-profile-modal");
const profileAvatarLarge = document.getElementById("profile-avatar-large");
const profileFileInput = document.getElementById("profile-file-input");
const profileSaveBtn = document.getElementById("profile-save-btn");
const profileDeleteBtn = document.getElementById("profile-delete-btn");
const profileModalMsg = document.getElementById("profile-modal-msg");
const profileNameVal = document.getElementById("profile-name-val");
const profileEmailVal = document.getElementById("profile-email-val");

let isWaiting = false;
let currentConversationId = null;
let currentUser = null;
let pendingProfilePicFile = null;


// ==========================================
// USER AVATAR & INITIALS HELPERS
// ==========================================

function getUserInitials(nameOrEmail) {
    if (!nameOrEmail) return "U";
    const parts = nameOrEmail.trim().split(/\s+/);
    if (parts.length >= 2 && parts[0] && parts[1]) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return nameOrEmail.substring(0, 2).toUpperCase();
}

function renderUserAvatars() {
    if (!currentUser) return;

    const initials = getUserInitials(currentUser.full_name || currentUser.email);
    const sidebarAvatar = document.getElementById("sidebar-user-avatar");

    if (sidebarAvatar) {
        if (currentUser.profile_picture) {
            sidebarAvatar.innerHTML = `<img src="${API_URL}${currentUser.profile_picture}" class="avatar-img" alt="Avatar">`;
        } else {
            sidebarAvatar.innerHTML = `<span id="sidebar-user-initials">${escapeHtml(initials)}</span>`;
        }
    }

    if (userDisplay) {
        userDisplay.textContent = currentUser.full_name || currentUser.email;
        userDisplay.title = currentUser.email;
    }

    // Update existing user message avatars in the active chat view
    const userMsgAvatars = document.querySelectorAll(".message-row[data-role='user'] .message-avatar");
    userMsgAvatars.forEach(av => {
        if (currentUser.profile_picture) {
            av.innerHTML = `<img src="${API_URL}${currentUser.profile_picture}" class="message-avatar-img" alt="Avatar">`;
        } else {
            av.textContent = initials;
        }
    });
}


// ==========================================
// PROFILE MODAL HANDLERS
// ==========================================

function renderModalAvatar(previewDataUrl = null) {
    if (!profileAvatarLarge) return;

    if (previewDataUrl) {
        profileAvatarLarge.innerHTML = `<img src="${previewDataUrl}" alt="Preview">`;
        return;
    }

    if (currentUser && currentUser.profile_picture) {
        profileAvatarLarge.innerHTML = `<img src="${API_URL}${currentUser.profile_picture}" alt="Avatar">`;
        if (profileDeleteBtn) profileDeleteBtn.style.display = "inline-block";
    } else {
        const initials = currentUser ? getUserInitials(currentUser.full_name || currentUser.email) : "U";
        profileAvatarLarge.innerHTML = `<span>${escapeHtml(initials)}</span>`;
        if (profileDeleteBtn) profileDeleteBtn.style.display = "none";
    }
}

function openProfileModal() {
    if (!currentUser || !profileModal) return;

    if (profileNameVal) profileNameVal.textContent = currentUser.full_name || "N/A";
    if (profileEmailVal) profileEmailVal.textContent = currentUser.email || "N/A";
    if (profileModalMsg) {
        profileModalMsg.textContent = "";
        profileModalMsg.className = "profile-modal-msg";
    }

    pendingProfilePicFile = null;
    if (profileFileInput) profileFileInput.value = "";
    if (profileSaveBtn) profileSaveBtn.style.display = "none";

    renderModalAvatar();
    profileModal.classList.add("open");
}

function closeProfileModalDialog() {
    if (profileModal) profileModal.classList.remove("open");
    pendingProfilePicFile = null;
}

if (userProfileBtn) {
    userProfileBtn.addEventListener("click", openProfileModal);
}

if (closeProfileModal) {
    closeProfileModal.addEventListener("click", closeProfileModalDialog);
}

if (profileModal) {
    profileModal.addEventListener("click", function(e) {
        if (e.target === profileModal) {
            closeProfileModalDialog();
        }
    });
}

if (profileFileInput) {
    profileFileInput.addEventListener("change", function(e) {
        const file = e.target.files[0];
        if (!file) return;

        if (file.size > 5 * 1024 * 1024) {
            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg error";
                profileModalMsg.textContent = "File is too large. Maximum size is 5MB.";
            }
            return;
        }

        const validTypes = ["image/jpeg", "image/png", "image/webp"];
        if (!validTypes.includes(file.type)) {
            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg error";
                profileModalMsg.textContent = "Please select a valid JPEG, PNG, or WebP image.";
            }
            return;
        }

        pendingProfilePicFile = file;

        const reader = new FileReader();
        reader.onload = function(evt) {
            renderModalAvatar(evt.target.result);
            if (profileSaveBtn) profileSaveBtn.style.display = "inline-block";
            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg";
                profileModalMsg.textContent = "Picture preview ready. Click Save Picture to apply.";
            }
        };
        reader.readAsDataURL(file);
    });
}

if (profileSaveBtn) {
    profileSaveBtn.addEventListener("click", async function() {
        if (!pendingProfilePicFile) return;

        profileSaveBtn.disabled = true;
        if (profileModalMsg) {
            profileModalMsg.className = "profile-modal-msg";
            profileModalMsg.textContent = "Uploading profile picture...";
        }

        const formData = new FormData();
        formData.append("file", pendingProfilePicFile);

        try {
            const response = await fetch(`${API_URL}/auth/profile-picture`, {
                method: "POST",
                credentials: "include",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Upload failed.");
            }

            currentUser.profile_picture = data.profile_picture;
            pendingProfilePicFile = null;
            profileSaveBtn.style.display = "none";
            renderUserAvatars();
            renderModalAvatar();

            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg success";
                profileModalMsg.textContent = "Profile picture updated successfully!";
            }

        } catch (err) {
            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg error";
                profileModalMsg.textContent = err.message;
            }
        } finally {
            profileSaveBtn.disabled = false;
        }
    });
}

if (profileDeleteBtn) {
    profileDeleteBtn.addEventListener("click", async function() {
        if (!confirm("Are you sure you want to remove your profile picture?")) return;

        profileDeleteBtn.disabled = true;

        try {
            const response = await fetch(`${API_URL}/auth/profile-picture`, {
                method: "DELETE",
                credentials: "include"
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to remove picture.");
            }

            currentUser.profile_picture = null;
            pendingProfilePicFile = null;
            if (profileSaveBtn) profileSaveBtn.style.display = "none";
            renderUserAvatars();
            renderModalAvatar();

            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg success";
                profileModalMsg.textContent = "Profile picture removed successfully.";
            }

        } catch (err) {
            if (profileModalMsg) {
                profileModalMsg.className = "profile-modal-msg error";
                profileModalMsg.textContent = err.message;
            }
        } finally {
            profileDeleteBtn.disabled = false;
        }
    });
}


// ==========================================
// AUTHENTICATION CHECK & INITIALIZATION
// ==========================================

async function checkSession() {
    try {
        const response = await fetch(`${API_URL}/auth/me`, {
            method: "GET",
            credentials: "include"
        });

        if (!response.ok) {
            window.location.href = "login.html";
            return;
        }

        const data = await response.json();
        currentUser = data.user;

        renderUserAvatars();

        // Initialize status and conversations
        loadAppStatus();
        loadConversations();

    } catch (error) {
        console.error("Session check error:", error);
        window.location.href = "login.html";
    }
}


// ==========================================
// LOAD ENGINE STATUS
// ==========================================

async function loadAppStatus() {
    try {
        const response = await fetch(`${API_URL}/`, {
            method: "GET"
        });

        if (response.ok) {
            const data = await response.json();
            if (statusText) {
                const engineName = data.model || data.intelligence_engine || "LEO AI";
                statusText.textContent = engineName;
            }
        }
    } catch (error) {
        console.warn("Status fetch failed:", error);
    }
}


// ==========================================
// LOGOUT
// ==========================================

if (logoutBtn) {
    logoutBtn.addEventListener("click", async function() {
        try {
            await fetch(`${API_URL}/auth/logout`, {
                method: "POST",
                credentials: "include"
            });
        } catch (error) {
            console.error("Logout request error:", error);
        } finally {
            window.location.href = "login.html";
        }
    });
}


// ==========================================
// MOBILE SIDEBAR TOGGLE
// ==========================================

function closeMobileSidebar() {
    if (sidebar) sidebar.classList.remove("open");
    if (sidebarBackdrop) sidebarBackdrop.classList.remove("open");
}

if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function() {
        if (sidebar) sidebar.classList.toggle("open");
        if (sidebarBackdrop) sidebarBackdrop.classList.toggle("open");
    });
}

if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", closeMobileSidebar);
}


// ==========================================
// CONVERSATION SIDEBAR MANAGEMENT
// ==========================================

async function loadConversations() {
    if (!conversationList) return;

    try {
        const response = await fetch(`${API_URL}/conversations`, {
            method: "GET",
            credentials: "include"
        });

        if (!response.ok) {
            return;
        }

        const conversations = await response.json();
        renderConversationList(conversations);

    } catch (error) {
        console.error("Error loading conversations:", error);
    }
}


function renderConversationList(conversations) {
    if (!conversationList) return;

    conversationList.innerHTML = "";

    if (!Array.isArray(conversations) || conversations.length === 0) {
        const emptyNotice = document.createElement("div");
        emptyNotice.className = "sidebar-info";
        emptyNotice.style.fontSize = "12px";
        emptyNotice.style.textTransform = "none";
        emptyNotice.textContent = "No conversations yet";
        conversationList.appendChild(emptyNotice);
        return;
    }

    conversations.forEach((conv) => {
        const item = document.createElement("div");
        item.className = "conversation-item";
        if (conv.id === currentConversationId) {
            item.classList.add("active");
        }

        const titleSpan = document.createElement("span");
        titleSpan.className = "conv-title";
        titleSpan.textContent = conv.title || "Untitled chat";
        titleSpan.title = "Click to open, double-click to rename";
        titleSpan.addEventListener("dblclick", function(event) {
            event.stopPropagation();
            renameConversationPrompt(conv.id, conv.title || "Untitled chat");
        });

        const actionsDiv = document.createElement("div");
        actionsDiv.className = "conv-actions";

        const renameBtn = document.createElement("button");
        renameBtn.className = "conv-action-btn rename-conv-btn";
        renameBtn.innerHTML = "✏️";
        renameBtn.title = "Rename conversation";
        renameBtn.setAttribute("aria-label", "Rename conversation");
        renameBtn.addEventListener("click", function(event) {
            event.stopPropagation();
            renameConversationPrompt(conv.id, conv.title || "Untitled chat");
        });

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "conv-action-btn delete-conv-btn";
        deleteBtn.innerHTML = "🗑️";
        deleteBtn.title = "Delete conversation";
        deleteBtn.setAttribute("aria-label", "Delete conversation");
        deleteBtn.addEventListener("click", function(event) {
            event.stopPropagation();
            deleteConversation(conv.id);
        });

        actionsDiv.appendChild(renameBtn);
        actionsDiv.appendChild(deleteBtn);

        item.appendChild(titleSpan);
        item.appendChild(actionsDiv);

        item.addEventListener("click", function() {
            if (!isWaiting) {
                closeMobileSidebar();
                selectConversation(conv.id);
            }
        });

        conversationList.appendChild(item);
    });
}


async function selectConversation(convId) {
    try {
        const response = await fetch(`${API_URL}/conversations/${convId}`, {
            method: "GET",
            credentials: "include"
        });

        if (!response.ok) {
            throw new Error("Unable to load conversation.");
        }

        const data = await response.json();
        currentConversationId = data.id;

        // Clear chat view
        chatMessages.innerHTML = "";

        // Highlight active item in sidebar
        const items = document.querySelectorAll(".conversation-item");
        items.forEach((item) => {
            const titleEl = item.querySelector(".conv-title");
            if (titleEl && titleEl.textContent === data.title) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });

        // Render past messages
        if (Array.isArray(data.messages) && data.messages.length > 0) {
            data.messages.forEach((msg) => {
                const roleLabel = msg.role === "user" ? "You" : "LEO";
                addMessage(roleLabel, msg.content, [], msg.id);
            });
        } else {
            renderWelcomeScreen();
        }

        loadConversations();

    } catch (error) {
        console.error("Failed to load conversation:", error);
    }
}


async function deleteConversation(convId) {
    if (!confirm("Are you sure you want to delete this conversation?")) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/conversations/${convId}`, {
            method: "DELETE",
            credentials: "include"
        });

        if (!response.ok) {
            throw new Error("Failed to delete conversation.");
        }

        if (currentConversationId === convId) {
            startNewChat();
        } else {
            loadConversations();
        }

    } catch (error) {
        console.error("Delete conversation error:", error);
    }
}


async function renameConversationPrompt(convId, currentTitle) {
    const newTitle = prompt("Enter a new title for this conversation:", currentTitle);
    if (!newTitle || newTitle.trim() === "" || newTitle.trim() === currentTitle) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/conversations/${convId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ title: newTitle.trim() })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Failed to rename conversation.");
        }

        loadConversations();
    } catch (error) {
        console.error("Rename conversation error:", error);
    }
}


async function deleteMessage(messageId, rowElement) {
    if (!currentConversationId || !messageId) return;

    if (!confirm("Are you sure you want to delete this message?")) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/conversations/${currentConversationId}/messages/${messageId}`, {
            method: "DELETE",
            credentials: "include"
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Failed to delete message.");
        }

        rowElement.remove();

        const remainingRows = chatMessages.querySelectorAll(".message-row");
        if (remainingRows.length === 0) {
            renderWelcomeScreen();
        }

    } catch (error) {
        console.error("Delete message error:", error);
        alert("Failed to delete message: " + error.message);
    }
}


function renderWelcomeScreen() {
    chatMessages.innerHTML = `
        <div class="welcome-screen" id="welcome-screen">
            <div class="welcome-logo">L</div>
            <h1>How can I help you?</h1>
            <p>Welcome to LEO, your personal AI assistant.</p>
        </div>
    `;
}


function startNewChat() {
    if (isWaiting) return;

    currentConversationId = null;
    renderWelcomeScreen();
    closeMobileSidebar();

    // Deselect active conversation item
    const activeItems = document.querySelectorAll(".conversation-item.active");
    activeItems.forEach((item) => item.classList.remove("active"));

    messageInput.value = "";
    messageInput.style.height = "auto";
    messageInput.focus();

    loadConversations();
}


// ==========================================
// MARKDOWN & CODE RENDERING
// ==========================================

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

window.copyCode = function(button) {
    const container = button.closest(".code-block-container");
    const codeElement = container ? container.querySelector("pre code") : null;
    if (!codeElement) return;

    const textToCopy = codeElement.textContent;
    navigator.clipboard.writeText(textToCopy).then(() => {
        const originalText = button.textContent;
        button.textContent = "Copied!";
        button.classList.add("copied");
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove("copied");
        }, 2000);
    }).catch(err => {
        console.error("Copy failed:", err);
    });
};

function renderMarkdown(content) {
    if (!content) return "";

    const codeBlocks = [];
    let processed = content.replace(/```([a-zA-Z0-9_\-\.\+]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push({
            lang: lang.trim() || "code",
            code: code.replace(/\n$/, "")
        });
        return `__CODE_BLOCK_${index}__`;
    });

    processed = escapeHtml(processed);

    processed = processed.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    processed = processed.replace(/^### (.*$)/gim, '<h4 class="md-heading">$1</h4>');
    processed = processed.replace(/^## (.*$)/gim, '<h3 class="md-heading">$1</h3>');
    processed = processed.replace(/^# (.*$)/gim, '<h2 class="md-heading">$1</h2>');

    processed = processed.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
    processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    processed = processed.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    processed = processed.replace(/^> (.*$)/gim, '<blockquote class="md-quote">$1</blockquote>');
    processed = processed.replace(/^\s*[-*]\s+(.*)$/gim, '<li class="md-li">$1</li>');
    processed = processed.replace(/(<li class="md-li">[\s\S]*?<\/li>)/g, '<ul class="md-ul">$1</ul>');
    processed = processed.replace(/<\/ul>\s*<ul class="md-ul">/g, '');

    processed = processed.replace(/\[(\d+)\]/g, '<span class="citation-badge" title="Citation [$1]">[$1]</span>');
    processed = processed.replace(/\n\n/g, '<br><br>');
    processed = processed.replace(/\n/g, '<br>');

    processed = processed.replace(/__CODE_BLOCK_(\d+)__/g, (match, index) => {
        const block = codeBlocks[Number(index)];
        if (!block) return "";
        const escapedCode = escapeHtml(block.code);
        const escapedLang = escapeHtml(block.lang);
        return `
            <div class="code-block-container">
                <div class="code-header">
                    <span class="code-lang">${escapedLang}</span>
                    <button class="copy-code-btn" type="button" onclick="copyCode(this)">Copy</button>
                </div>
                <pre><code class="language-${escapedLang}">${escapedCode}</code></pre>
            </div>
        `;
    });

    return processed;
}


// ==========================================
// CREATE MESSAGE BUBBLE
// ==========================================

function addMessage(role, content, sources = [], messageId = null) {
    const welcome = document.getElementById("welcome-screen");
    if (welcome) {
        welcome.remove();
    }

    const row = document.createElement("div");
    row.className = "message-row";
    row.setAttribute("data-role", role === "You" ? "user" : "assistant");
    if (messageId) {
        row.setAttribute("data-message-id", messageId);
    }

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    if (role === "You") {
        if (currentUser && currentUser.profile_picture) {
            avatar.innerHTML = `<img src="${API_URL}${currentUser.profile_picture}" class="message-avatar-img" alt="User Avatar">`;
        } else {
            const initials = currentUser ? getUserInitials(currentUser.full_name || currentUser.email) : "Y";
            avatar.textContent = initials;
        }
    } else {
        avatar.textContent = "L";
    }

    const contentBox = document.createElement("div");
    contentBox.className = "message-body";

    const topHeader = document.createElement("div");
    topHeader.className = "message-top-header";

    const roleLabel = document.createElement("div");
    roleLabel.className = "message-role";
    roleLabel.textContent = role;

    topHeader.appendChild(roleLabel);

    if (messageId && currentConversationId) {
        const actionsSpan = document.createElement("div");
        actionsSpan.className = "message-actions";

        const delMsgBtn = document.createElement("button");
        delMsgBtn.className = "message-action-btn delete-msg-btn";
        delMsgBtn.innerHTML = "🗑️";
        delMsgBtn.title = "Delete this message";
        delMsgBtn.setAttribute("aria-label", "Delete this message");
        delMsgBtn.addEventListener("click", function(event) {
            event.stopPropagation();
            deleteMessage(messageId, row);
        });

        actionsSpan.appendChild(delMsgBtn);
        topHeader.appendChild(actionsSpan);
    }

    const messageText = document.createElement("div");
    messageText.className = "message-content";

    if (role === "LEO") {
        messageText.innerHTML = renderMarkdown(content);
    } else {
        messageText.innerHTML = escapeHtml(content).replace(/\n/g, "<br>");
    }

    contentBox.appendChild(topHeader);
    contentBox.appendChild(messageText);

    // Display web sources if available
    if (role === "LEO" && Array.isArray(sources) && sources.length > 0) {
        const sourcesContainer = document.createElement("div");
        sourcesContainer.className = "message-sources";

        const sourcesHeading = document.createElement("div");
        sourcesHeading.className = "sources-heading";
        sourcesHeading.textContent = "Sources";
        sourcesContainer.appendChild(sourcesHeading);

        sources.forEach((source) => {
            if (!source.title || !source.url) return;

            try {
                const parsedUrl = new URL(source.url);
                if (!["http:", "https:"].includes(parsedUrl.protocol)) return;

                const link = document.createElement("a");
                link.className = "source-link";
                link.href = parsedUrl.href;
                link.textContent = source.title;
                link.target = "_blank";
                link.rel = "noopener noreferrer";

                sourcesContainer.appendChild(link);
            } catch (error) {
                console.warn("Invalid source URL:", source.url);
            }
        });

        if (sourcesContainer.children.length > 1) {
            contentBox.appendChild(sourcesContainer);
        }
    }

    row.appendChild(avatar);
    row.appendChild(contentBox);

    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return row;
}


// ==========================================
// THINKING INDICATOR
// ==========================================

function isLikelyResourceSearch(msg) {
    const text = msg.toLowerCase().trim();
    const patterns = [
        /\b(latest|breaking|recent|today'?s?)\s+(news|headlines?|events?|updates?)\b/,
        /\bcurrent\s+(price|stock|rate|weather|forecast|score|standing)\b/,
        /\b(stock|crypto|bitcoin|btc|ethereum|eth|gold)\s+price\b/,
        /\b(latest|newest|recent)\s+(version|release|changelog|features?)\b/,
        /\b(courses?|certifications?|tutorials?|learning\s+resources?|syllabus)\b/,
        /\b(official\s+docs?|official\s+documentation|api\s+docs?|api\s+reference)\b/,
        /\b(research\s+papers?|arxiv|whitepapers?)\b/,
        /\b(search\s+(the\s+)?(web|internet|online)|look\s+up\s+online|find\s+online)\b/
    ];
    return patterns.some(p => p.test(text));
}

function showThinkingIndicator(isResearching = false) {
    removeThinkingIndicator();

    const welcome = document.getElementById("welcome-screen");
    if (welcome) {
        welcome.remove();
    }

    const row = document.createElement("div");
    row.className = "message-row typing-row";
    row.id = "leo-thinking-indicator";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "L";

    const contentBox = document.createElement("div");
    contentBox.className = "message-body";

    const roleLabel = document.createElement("div");
    roleLabel.className = "message-role";
    roleLabel.textContent = "LEO";

    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.setAttribute("aria-live", "polite");

    const status = document.createElement("span");
    status.className = "typing-status";
    status.textContent = isResearching ? "LEO is researching..." : "LEO is thinking...";

    const dots = document.createElement("div");
    dots.className = "typing-dots";

    for (let i = 0; i < 3; i++) {
        const dot = document.createElement("span");
        dot.className = "typing-dot";
        dots.appendChild(dot);
    }

    indicator.appendChild(status);
    indicator.appendChild(dots);

    contentBox.appendChild(roleLabel);
    contentBox.appendChild(indicator);

    row.appendChild(avatar);
    row.appendChild(contentBox);

    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


function removeThinkingIndicator() {
    const indicator = document.getElementById("leo-thinking-indicator");
    if (indicator) {
        indicator.remove();
    }
}


// ==========================================
// SEND MESSAGE TO LEO
// ==========================================

async function sendMessage(message) {
    if (isWaiting) return;

    isWaiting = true;

    // Show user message in UI
    const userRow = addMessage("You", message);
    sendButton.disabled = true;

    const searchEnabled = searchToggle ? searchToggle.checked : false;
    const isResearching = searchEnabled && isLikelyResourceSearch(message);
    showThinkingIndicator(isResearching);

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({
                message: message,
                conversation_id: currentConversationId,
                max_new_tokens: searchEnabled ? 200 : 500,
                temperature: 0.4,
                search_enabled: searchEnabled
            })
        });

        const data = await response.json();

        if (response.status === 401) {
            window.location.href = "login.html";
            return;
        }

        if (!response.ok) {
            throw new Error(data.detail || `Server error: ${response.status}`);
        }

        if (!data.response) {
            throw new Error("LEO returned an empty response.");
        }

        removeThinkingIndicator();

        // Update active conversation ID and attach message ID if available
        currentConversationId = data.conversation_id;

        // If user message ID is returned, attach it to user row
        if (data.user_message_id && userRow) {
            userRow.setAttribute("data-message-id", data.user_message_id);
            const userHeader = userRow.querySelector(".message-top-header");
            if (userHeader && !userHeader.querySelector(".message-actions")) {
                const actionsSpan = document.createElement("div");
                actionsSpan.className = "message-actions";
                const delMsgBtn = document.createElement("button");
                delMsgBtn.className = "message-action-btn delete-msg-btn";
                delMsgBtn.innerHTML = "🗑️";
                delMsgBtn.title = "Delete this message";
                delMsgBtn.addEventListener("click", function(event) {
                    event.stopPropagation();
                    deleteMessage(data.user_message_id, userRow);
                });
                actionsSpan.appendChild(delMsgBtn);
                userHeader.appendChild(actionsSpan);
            }
        }

        addMessage("LEO", data.response, data.sources || [], data.message_id || null);

        // Refresh sidebar conversation titles
        loadConversations();

    } catch (error) {
        console.error("LEO API Error:", error);
        removeThinkingIndicator();
        addMessage("LEO", "Unable to connect to LEO: " + error.message);

    } finally {
        removeThinkingIndicator();
        isWaiting = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}


// ==========================================
// EVENT LISTENERS
// ==========================================

chatForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const message = messageInput.value.trim();
    if (!message || isWaiting) return;

    messageInput.value = "";
    messageInput.style.height = "auto";

    await sendMessage(message);
});


newChatButton.addEventListener("click", function() {
    startNewChat();
});


messageInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chatForm.requestSubmit();
    }
});


messageInput.addEventListener("input", function() {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 140) + "px";
});


// Start session verification on load
checkSession();
