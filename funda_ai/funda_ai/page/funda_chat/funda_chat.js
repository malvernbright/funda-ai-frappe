frappe.pages['funda_chat'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Socratic Tutor',
        single_column: true
    });

    // Render the HTML template
    $(frappe.render_template("funda_chat", {})).appendTo(page.main);

    // State Variables
    let chatHistory = [];

    // DOM Elements
    const $messages = $('#funda-messages');
    const $input = $('#funda-input');
    const $submit = $('#funda-submit');
    const $tier = $('#funda-tier');

    function appendMessage(role, content) {
        const rowClass = role === 'user' ? 'funda-msg-row user' : 'funda-msg-row assistant';
        const boxClass = role === 'user' ? 'funda-msg-box user' : 'funda-msg-box assistant';

        const msgHtml = `
            <div class="${rowClass}">
                <div class="${boxClass}">${content}</div>
            </div>
        `;
        $messages.append(msgHtml);
        $messages.scrollTop($messages[0].scrollHeight);
    }

    function sendMessage() {
        const message = $input.val().trim();
        if (!message) return;

        // 1. Update UI for User
        appendMessage('user', message);
        $input.val('');
        $submit.prop('disabled', true);

        // Add loading indicator
        const loadingId = 'loading-' + Date.now();
        $messages.append(`<div id="${loadingId}" class="funda-msg-row assistant"><div class="funda-msg-box assistant">...thinking...</div></div>`);
        $messages.scrollTop($messages[0].scrollHeight);

        // 2. Call Frappe Backend
        frappe.call({
            method: "funda_ai.funda_ai.api.chat_with_funda",
            args: {
                message: message,
                tier: $tier.val(),
                history: JSON.stringify(chatHistory)
            },
            callback: function (r) {
                // Remove loading indicator
                $(`#${loadingId}`).remove();
                $submit.prop('disabled', false);
                $input.focus();

                if (r.message && r.message.status === "success") {
                    const aiReply = r.message.reply;
                    appendMessage('assistant', aiReply);

                    // Update Context History for Ollama
                    chatHistory.push({ "role": "user", "content": message });
                    chatHistory.push({ "role": "assistant", "content": aiReply });

                    // Keep history brief to save RAM on edge hardware
                    if (chatHistory.length > 10) {
                        chatHistory = chatHistory.slice(chatHistory.length - 10);
                    }
                } else {
                    appendMessage('assistant', "I'm having trouble connecting to the knowledge base. Let's try again in a moment.");
                }
            }
        });
    }

    // Event Listeners
    $submit.on('click', sendMessage);
    $input.on('keypress', function (e) {
        if (e.which === 13) {
            sendMessage();
        }
    });
};