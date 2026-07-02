frappe.pages['funda_chat'].on_page_load = function (wrapper) {
    // Safely load external libraries avoiding the appendChild crash
    frappe.require([
        "/assets/funda_ai/js/marked.min.js",
        "/assets/funda_ai/css/katex.min.css",
        "/assets/funda_ai/js/katex.min.js"
    ], function() {
        frappe.require("/assets/funda_ai/js/auto-render.min.js", function() {
            initFundaChat(wrapper);
        });
    });
};

function initFundaChat(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Socratic Tutor',
        single_column: true
    });

    $(frappe.render_template("funda_chat", {})).appendTo(page.main);

    // State Variables
    let chatHistory = [];
    let currentSessionName = null; 
    const $messages = $('#funda-messages');
    const $input = $('#funda-input');
    const $submit = $('#funda-submit');
    const $tier = $('#funda-tier');
    const $historyList = $('#funda-history-list');
    const $newChatBtn = $('#funda-new-chat');

    function loadSidebarHistory() {
        frappe.call({
            method: "funda_ai.funda_ai.api.get_user_sessions",
            callback: function (r) {
                $historyList.empty();
                if (r.message && r.message.status === "success" && r.message.sessions.length > 0) {
                    r.message.sessions.forEach(session => {
                        const activeClass = session.name === currentSessionName ? 'background-color: #333537;' : '';
                        const itemHtml = `
                            <div class="funda-history-item" data-session="${session.name}" 
                                 style="padding: 10px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #e3e3e3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background 0.2s; ${activeClass}">
                                💬 ${session.topic}
                            </div>
                        `;
                        $historyList.append(itemHtml);
                    });
                } else {
                    $historyList.append('<div style="font-size: 12px; color: #6b7280; text-align: center; margin-top: 20px;">No chat history found</div>');
                }
            }
        });
    }

    function loadSessionMessages(sessionName) {
        $messages.empty();
        chatHistory = [];
        currentSessionName = sessionName;
        
        $messages.append('<div class="funda-msg-row assistant"><div class="funda-msg-box assistant">Loading...</div></div>');

        frappe.call({
            method: "funda_ai.funda_ai.api.get_session_messages",
            args: { session_name: sessionName },
            callback: function (r) {
                $messages.empty();
                if (r.message && r.message.status === "success") {
                    r.message.messages.forEach(msg => {
                        appendMessage(msg.role, msg.content);
                        chatHistory.push({ "role": msg.role, "content": msg.content });
                    });
                    loadSidebarHistory(); 
                }
            }
        });
    }

    function appendMessage(role, content) {
        let parsedContent = marked.parse(content);
        const rowClass = role === 'user' ? 'funda-msg-row user' : 'funda-msg-row assistant';
        const boxClass = role === 'user' ? 'funda-msg-box user' : 'funda-msg-box assistant';

        const msgHtml = `
            <div class="${rowClass}">
                <div class="${boxClass}">${parsedContent}</div>
            </div>
        `;
        $messages.append(msgHtml);
        
        renderMathInElement($messages[0], {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false }
            ]
        });
        $messages.scrollTop($messages[0].scrollHeight);
    }

    function sendMessage() {
        const message = $input.val().trim();
        if (!message) return;

        appendMessage('user', message);
        $input.val('');
        $input.css('height', 'auto');
        $submit.prop('disabled', true);
        
        const loadingId = 'loading-' + Date.now();
        $messages.append(`<div id="${loadingId}" class="funda-msg-row assistant"><div class="funda-msg-box assistant">...thinking...</div></div>`);
        $messages.scrollTop($messages[0].scrollHeight);

        frappe.call({
            method: "funda_ai.funda_ai.api.chat_with_funda",
            args: {
                message: message,
                tier: $tier.val(),
                history: JSON.stringify(chatHistory),
                session_name: currentSessionName
            },
            callback: function (r) {
                $(`#${loadingId}`).remove();
                $submit.prop('disabled', false);
                $input.focus();

                if (r.message && r.message.status === "success") {
                    currentSessionName = r.message.session_name; 
                    loadSidebarHistory(); 
                    
                    const aiReply = r.message.reply;
                    appendMessage('assistant', aiReply);

                    chatHistory.push({ "role": "user", "content": message });
                    chatHistory.push({ "role": "assistant", "content": aiReply });

                    if (chatHistory.length > 10) {
                        chatHistory = chatHistory.slice(chatHistory.length - 10);
                    }
                } else {
                    appendMessage('assistant', "I'm having trouble connecting to the knowledge base. Let's try again in a moment.");
                }
            }
        });
    }

    // Initialize Sidebar
    loadSidebarHistory();

    // Listeners
    $historyList.on('click', '.funda-history-item', function() {
        const sessionName = $(this).data('session');
        loadSessionMessages(sessionName);
    });

    $newChatBtn.on('click', function() {
        currentSessionName = null;
        chatHistory = [];
        $messages.empty();
        loadSidebarHistory();
        appendMessage('assistant', "Hi! I am Funda, your Heritage-Based Curriculum guide. What stage of your project are you working on today?");
    });

    $submit.on('click', sendMessage);

    $input.on('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    $input.on('keydown', function (e) {
        if (e.which === 13 && !e.shiftKey) {
            e.preventDefault(); 
            sendMessage();
        }
    });
}