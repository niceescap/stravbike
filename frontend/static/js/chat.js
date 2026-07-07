/* ═══════════════════════════════════════════════════════════
   chat.js — Widget chat avec streaming SSE
   Proxy: POST /api/chat/ → OpenWebUI (modèle + tool stravbike)
   ═══════════════════════════════════════════════════════════ */

const Chat = {
    messagesEl: null,
    inputEl: null,
    sendBtn: null,
    sending: false,

    init() {
        this.messagesEl = document.getElementById('chat-messages');
        this.inputEl    = document.getElementById('chat-input');
        this.sendBtn    = document.getElementById('chat-send');
        if (this.inputEl) this.inputEl.focus();
    },

    onKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.send();
        }
    },

    async send() {
        if (this.sending) return;
        const message = this.inputEl?.value?.trim();
        if (!message) return;

        // Supprimer le message d'accueil
        const welcome = this.messagesEl?.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // Afficher le message utilisateur
        this._addMessage('user', message);
        this.inputEl.value = '';
        this.inputEl.style.height = 'auto';
        this._setSending(true);

        // Créer le placeholder assistant
        const assistantEl = this._addMessage('assistant', '');
        const contentEl = assistantEl.querySelector('.chat-bubble');
        contentEl.innerHTML = '<span class="spinner"></span>';

        try {
            const response = await fetch('/api/chat/', {
                method: 'POST',
                headers: {
                    'X-API-Key': App.SERVICE_KEY,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            contentEl.innerHTML = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value, { stream: true });
                const lines = text.split('\n');

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') break;
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.content) {
                            fullText += parsed.content;
                            contentEl.innerHTML = this._renderMarkdown(fullText);
                            this._scrollToBottom();
                        }
                    } catch (e) { continue; }
                }
            }

            if (!fullText) {
                contentEl.textContent = 'Pas de réponse.';
            }
        } catch (e) {
            contentEl.textContent = 'Erreur : ' + e.message;
        } finally {
            this._setSending(false);
        }
    },

    _setSending(state) {
        this.sending = state;
        if (this.sendBtn) this.sendBtn.disabled = state;
        if (this.inputEl) this.inputEl.disabled = state;
        if (!state && this.inputEl) this.inputEl.focus();
    },

    _addMessage(role, content) {
        const el = document.createElement('div');
        el.className = `chat-message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = `chat-avatar ${role}`;
        avatar.textContent = role === 'user' ? 'N' : '🤖';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble';
        bubble.innerHTML = this._renderMarkdown(content);

        el.appendChild(avatar);
        el.appendChild(bubble);
        this.messagesEl.appendChild(el);
        this._scrollToBottom();
        return el;
    },

    _renderMarkdown(text) {
        if (!text) return '';
        // Échapper HTML
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Code blocks
        html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) =>
            `<pre><code>${code.trim()}</code></pre>`);

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Headers
        html = html.replace(/^### (.+)$/gm, '<p><strong>$1</strong></p>');
        html = html.replace(/^## (.+)$/gm, '<p><strong>$1</strong></p>');
        html = html.replace(/^# (.+)$/gm, '<p><strong>$1</strong></p>');

        // Listes
        html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
        html = html.replace(/<\/ul>\n<ul>/g, '');

        // Paragraphes (lignes non entourées de tags HTML)
        html = html.split('\n\n').map(block => {
            if (block.match(/^<(pre|ul|ol)/)) return block;
            if (block.trim() === '') return '';
            return block.replace(/\n/g, '<br>');
        }).join('\n');

        return html;
    },

    _scrollToBottom() {
        if (this.messagesEl) {
            this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
        }
    },
};
