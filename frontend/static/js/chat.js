/* ═══════════════════════════════════════════════════════════
   CHAT.JS — Widget chat → proxy OpenWebUI (streaming SSE)
   L'utilisateur discute avec le modèle personnalisé OpenWebUI
   qui a l'outil stravbike_tool.py rattaché.
═══════════════════════════════════════════════════════════ */

let chatHistory = [];
let isStreaming = false;

function getChatMessagesEl() { return document.getElementById('chat-messages'); }
function getChatInputEl() { return document.getElementById('chat-input'); }

/* ── Append message to DOM ── */
function appendMessage(role, content) {
    const container = getChatMessagesEl();
    if (!container) return;

    // Retirer le welcome
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const msg = document.createElement('div');
    msg.className = `chat-msg ${role}`;

    const avatar = document.createElement('div');
    avatar.className = `chat-msg-avatar ${role}`;
    avatar.textContent = role === 'assistant' ? '🚴' : 'N';

    const bubble = document.createElement('div');
    bubble.className = 'chat-msg-bubble';
    bubble.innerHTML = formatMarkdown(content);

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    return bubble;
}

/* ── Typing indicator ── */
function showTyping() {
    const container = getChatMessagesEl();
    if (!container) return;
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const msg = document.createElement('div');
    msg.className = 'chat-msg assistant';
    msg.id = 'typing-msg';

    const avatar = document.createElement('div');
    avatar.className = 'chat-msg-avatar assistant';
    avatar.textContent = '🚴';

    const bubble = document.createElement('div');
    bubble.className = 'chat-msg-bubble';
    bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typing-msg');
    if (el) el.remove();
}

/* ── Markdown basic ── */
function formatMarkdown(text) {
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

/* ── Send message to OpenWebUI via FastAPI proxy ── */
async function sendMessage() {
    const input = getChatInputEl();
    if (!input) return;
    const text = input.value.trim();
    if (!text || isStreaming) return;

    // Ajouter message utilisateur
    appendMessage('user', text);
    chatHistory.push({ role: 'user', content: text });

    input.value = '';
    input.style.height = 'auto';

    // Typing
    isStreaming = true;
    showTyping();

    try {
        const key = getServiceKey();
        const res = await fetch('/chat/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(key ? { 'X-API-Key': key } : {})
            },
            body: JSON.stringify({ messages: chatHistory })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        // Lire le stream SSE
        removeTyping();
        const assistantBubble = appendMessage('assistant', '');
        let fullText = '';

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(data);
                        const delta = parsed.choices?.[0]?.delta?.content || '';
                        if (delta) {
                            fullText += delta;
                            assistantBubble.innerHTML = formatMarkdown(fullText);
                            const container = getChatMessagesEl();
                            container.scrollTop = container.scrollHeight;
                        }
                    } catch(e) {}
                }
            }
        }

        if (!fullText) {
            assistantBubble.innerHTML = '<span style="color:var(--muted)">Aucune réponse reçue.</span>';
        }

        chatHistory.push({ role: 'assistant', content: fullText });
    } catch(e) {
        removeTyping();
        appendMessage('assistant', 'Erreur de connexion au coach IA. Vérifiez qu\'OpenWebUI est démarré et que OPENWEBUI_API_KEY est configuré.');
    } finally {
        isStreaming = false;
    }
}

/* ── Suggestion chips ── */
function sendSuggestion(text) {
    const input = getChatInputEl();
    if (input) {
        input.value = text;
        sendMessage();
    }
}

/* ── Init chat page ── */
document.addEventListener('DOMContentLoaded', () => {
    const input = getChatInputEl();
    if (!input) return;

    // Enter = send, Shift+Enter = newline
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });
});
