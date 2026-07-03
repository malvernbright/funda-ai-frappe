import logging
import frappe
import json
import socket
import ollama
from .rag_engine import query_local_rag
from .online_fallback import fetch_online_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are 'Funda', an encouraging, highly knowledgeable Zimbabwean master teacher and tutor. 
You are fully fluent in English, Shona, and Ndebele, and you always match the language and mix-tone used by the student.

CORE TUTORING PHILOSOPHY:
1. GROUNDING: Base your educational knowledge directly on the provided [Context] from local syllabi and textbooks. If the context does not contain relevant pedagogical framework, rely cleanly on standardized ZIMSEC and Cambridge curriculum principles. Never hallucinate facts.
2. SOCRATIC METHOD: Do not provide direct answers or write segments for the student. Guide them using structured inquiries, hints, and step-by-step conceptual scaffolding.
3. LANGUAGE INTEGRITY: If the student asks for technical concepts or scientific tasks in Shona or Ndebele, ensure accuracy by combining accurate native phrasing with proper technical definitions found in the context.

DYNAMIC ARCHITECTURAL MODES:
- MODE A: Project Mode (Heritage-Based Curriculum)
  Guide the student sequentially through the 6 core stages of their HBC project layout (Problem Identification, Investigation, Idea Generation, Refinement, Presentation, Evaluation). You are allowed to summarize project progress frameworks or display high-level stage requirements based on template documents when explicitly asked about layout roadmaps.
- MODE B: Tutoring Mode (General Academic Enrichment)
  Act as a smart, versatile multi-subject mentor covering Mathematics, English Language, Geography, and general sciences. Break complex concepts into clear, digestible learning milestones. Present formulas, explanations, and linguistic frameworks beautifully. Verify comprehension at the end of each sub-step before advancing to the next.
"""

def is_internet_available(host="8.8.8.8", port=53, timeout=2):
    """Check if the local server environment has real-world internet connectivity."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

@frappe.whitelist()
def chat_with_funda(message, tier="All Levels", mode="Project", subject="General", history="[]", session_name=None):
    """
    Unified Frappe API endpoint for the Funda Smart Tutor ecosystem.
    """
    try:
        # 1. Normalize frontend strings to match validation options inside DocTypes
        tier_map = {
            "all": "All Levels", "All Levels": "All Levels",
            "primary": "Primary", "Primary": "Primary",
            "junior_high": "Junior High", "Junior High": "Junior High",
            "senior_high": "Senior High", "Senior High": "Senior High"
        }
        actual_tier = tier_map.get(tier, "All Levels")
        chat_history = json.loads(history)
        
        # 2. Sliding Window Query Enrichment
        user_messages = [msg['content'] for msg in chat_history if msg['role'] == 'user']
        recent_context = " ".join(user_messages[-2:]) if user_messages else ""
        rag_search_query = f"{recent_context} {message}".strip()
        
        # 3. Subject-Separated Local RAG Execution
        # We lowercase inputs to align nicely with segmented subdirectory naming
        rag_context = query_local_rag(
            user_query=rag_search_query, 
            tier=actual_tier.lower().replace(" ", "_"), 
            subject=subject.lower()
        )
        
        # 4. Strict Offline-First Logic Gate
        # Online fallback runs ONLY in Project Mode when local assets are fully exhausted and web is verified
        if not rag_context.strip() and mode == "Project":
            if is_internet_available():
                try:
                    online_context = fetch_online_context(rag_search_query)
                    if online_context:
                        rag_context = f"[INTERNET SEARCH RESULTS]\n{online_context}"
                except Exception as net_err:
                    logger.warning(f"Resilient fallback triggered. Online crawl skipped: {net_err}")
            else:
                logger.info("Server operating in pure offline environment. Web fallback bypassed.")
        
        # 5. Injection Structure Building
        augmented_prompt = f"""
        [SYSTEM ARCHITECTURE PARAMETERS]
        Current Operational Mode: {mode} Mode
        Target Learning Subject: {subject}
        Syllabus Context Grounding:
        {rag_context if rag_context.strip() else "No direct localized materials retrieved. Teach via default curriculum guidelines."}
        
        [STUDENT INQUIRY]
        Question: {message}
        """
        
        # 6. Inference Assembly
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": augmented_prompt})
        
        response = ollama.chat(
            model="qwen2.5-coder:7b", 
            messages=messages
        )
        ai_reply = response['message']['content']
        success_response = {"status": "success", "reply": ai_reply, "session_name": session_name}
        
        # 7. Persistent Conversational Logging
        if not session_name:
            title = (message[:25] + '...') if len(message) > 25 else message
            new_session = frappe.get_doc({
                "doctype": "Funda Chat Session",
                "topic": title,
                "tier": actual_tier
            })
            new_session.insert(ignore_permissions=True)
            session_name = new_session.name
            success_response["session_name"] = session_name
            
        frappe.get_doc({
            "doctype": "Funda Chat Message",
            "session": session_name,
            "role": "user",
            "content": message
        }).insert(ignore_permissions=True)
        
        frappe.get_doc({
            "doctype": "Funda Chat Message",
            "session": session_name,
            "role": "assistant",
            "content": ai_reply
        }).insert(ignore_permissions=True)
        
        frappe.db.set_value("Funda Chat Session", session_name, "modified", frappe.utils.now())
        frappe.db.commit()
        
        # Keep background analytics stable
        frappe.get_doc({
            "doctype": "Tutor Analytics Log",
            "user": frappe.session.user,
            "query": message,
            "tier": actual_tier
        }).insert(ignore_permissions=True)
        
        return success_response

    except Exception as e:
        logger.error(f"Funda Endpoint Crash: {str(e)}")
        frappe.log_error(f"Funda AI Crash Log: {str(e)}", "Funda AI Chat Endpoint")
        return {"status": "error", "message": "Funda is currently taking a break. Please try again."}

@frappe.whitelist()
def get_user_sessions():
    """Fetches list of historical chat sessions unique to the current account context."""
    sessions = frappe.get_all(
        "Funda Chat Session",
        filters={"owner": frappe.session.user},
        fields=["name", "topic", "modified"],
        order_by="modified desc",
        limit=15
    )
    return {"status": "success", "sessions": sessions}

@frappe.whitelist()
def get_session_messages(session_name):
    """Retrieves full timeline ordering of a selected interaction block."""
    messages = frappe.get_all(
        "Funda Chat Message",
        filters={"session": session_name},
        fields=["role", "content", "creation"],
        order_by="creation asc"
    )
    return {"status": "success", "messages": messages}