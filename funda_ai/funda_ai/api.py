import logging
import frappe
import json
import string
import ollama
from .rag_engine import query_local_rag
from .online_fallback import fetch_online_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are 'Funda', an encouraging Zimbabwean teacher assisting a student with their Heritage-Based Curriculum (HBC) project. 
You are fluent in English, Shona, and Ndebele.

CORE RULES:
1. GROUNDING: Your answer must be derived ONLY from the provided [Context]. If the [Context] does not contain the answer in the language requested, state that you need more information from the syllabus. DO NOT guess.
2. LANGUAGE: Reply in the same language as the student's prompt. 
3. SOCRATIC METHOD: Ask guiding questions. Do not give the answer.
4. HALLUCINATION PREVENTION: If a student asks for scientific facts in Shona/Ndebele, strictly use the technical terms found in the provided [Context] to ensure accuracy.

CRITICAL LANGUAGE RULE: 
You fully understand English, Shona, and Ndebele. You MUST reply in the exact language the student uses. If they ask a question in Shona, reply in Shona. If they mix languages, match their tone.

PRIMARY DIRECTIVE:
Your default behavior is the Socratic method. Do not write the project for the student. Ask guiding questions to help them think critically about their local environment. 

HANDLING SPECIFIC REQUESTS:
- Scenario A (Tutoring): If the student is working on a specific stage, review the provided syllabus context and ask a single, guiding question. If they are stuck, give a small hint on what they should research.
- Scenario B (Progress & Templates): IF the student asks about the project's progress or what the final project should look like, YOU ARE EXPLICITLY ALLOWED to summarize the 6 stages based on the provided template context. Give them a high-level roadmap of the template, but remind them they must write their own specific details.
- Scenario C (Cheating): If the student asks you to do the work without putting in effort, politely decline and ask a question to get them started.
- Scenario D (Completion): Once the 6 stages are complete, compile their work so they can copy it.
"""

@frappe.whitelist()
def chat_with_funda(message, tier="All Levels", history="[]", session_name=None):
    """
    Frappe API endpoint replacing the FastAPI chat route.
    """
    try:
        # Map incoming frontend values to the exact DocType Select options
        tier_map = {
            "all": "All Levels",
            "primary": "Primary",
            "junior_high": "Junior High",
            "senior_high": "Senior High"
        }
        actual_tier = tier_map.get(tier, "All Levels")
        # 1. Parse history
        chat_history = json.loads(history)
        
        # 2. DYNAMIC TOPIC EXTRACTION FOR RAG
        # Extract previous user messages to maintain the topic in the vector search
        user_messages = [msg['content'] for msg in chat_history if msg['role'] == 'user']
        
        # Take up to the last 2 user messages + the current message to form a robust search query
        recent_context = " ".join(user_messages[-2:]) if user_messages else ""
        rag_search_query = f"{recent_context} {message}".strip()
        
        # Query local ChromaDB with the enriched query so it remembers the topic
        rag_context = query_local_rag(rag_search_query, tier)
        
        # If ChromaDB returns nothing, trigger the online fallback
        if not rag_context.strip():
            logging.debug("No local knowledge found. Triggering online fallback.")
            frappe.logger().info("No local knowledge found. Triggering online fallback.")
            rag_context = fetch_online_context(rag_search_query)
            
            # Append a note so the AI knows this is from the internet, not the syllabus
            if rag_context:
                rag_context = f"[INTERNET SEARCH RESULTS]\n{rag_context}"
        
        # 3. Build Socratic prompt with context
        augmented_prompt = f"""
        Context from HBC Syllabus & Templates:
        {rag_context if rag_context else "No specific syllabus context found for this query."}
        
        Student's Question: {message}
        """
        
        # 4. Construct messages array for Ollama
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": augmented_prompt})
        
        # 5. Call local Ollama model
        response = ollama.chat(
            model="qwen2.5-coder:7b", 
            messages=messages
        )
        
        ai_reply = response['message']['content']
        
        # success_response = {"status": "success", "reply": ai_reply}
        success_response = {"status": "success", "reply": ai_reply, "session_name": session_name}
        
        # --- DATABASE LOGGING ---
        # 1. Create a new session if one wasn't provided
        if not session_name:
            # Generate a short title from the user's message
            title = (message[:25] + '...') if len(message) > 25 else message
            
            new_session = frappe.get_doc({
                "doctype": "Funda Chat Session",
                "topic": title,
                "tier": actual_tier, # Use the mapped value here
                "owner": frappe.session.user
            })
            new_session.insert(ignore_permissions=True)
            session_name = new_session.name
            success_response["session_name"] = session_name
            
        # 2. Save the User's Message
        frappe.get_doc({
            "doctype": "Funda Chat Message",
            "session": session_name,
            "role": "user",
            "content": message
        }).insert(ignore_permissions=True)
        
        # 3. Save the AI's Reply
        frappe.get_doc({
            "doctype": "Funda Chat Message",
            "session": session_name,
            "role": "assistant",
            "content": ai_reply
        }).insert(ignore_permissions=True)
        
        # Update the session's modified date so it jumps to the top of the sidebar
        frappe.db.set_value("Funda Chat Session", session_name, "modified", frappe.utils.now())
        frappe.db.commit()
        
        # 6. Log the interaction to the Tutor Analytics Doctype
        frappe.get_doc({
            "doctype": "Tutor Analytics Log",
            "user": frappe.session.user,
            "query": message,
            "tier": tier
        }).insert(ignore_permissions=True)
        
        return success_response

    except Exception as e:
        logging.error(f"Funda AI Error: {str(e)}")
        frappe.log_error(f"Funda AI Error: {str(e)}", "Funda AI Chat Endpoint")
        return {"status": "error", "message": "Funda is currently taking a break. Please try again."}
    

@frappe.whitelist()
def get_user_sessions():
    """Fetches the sidebar history for the logged-in student."""
    sessions = frappe.get_all(
        "Funda Chat Session",
        filters={"owner": frappe.session.user}, # Only show their own chats
        fields=["name", "topic", "modified"],
        order_by="modified desc",
        limit=15
    )
    return {"status": "success", "sessions": sessions}

@frappe.whitelist()
def get_session_messages(session_name):
    """Fetches the full conversation when a sidebar item is clicked."""
    messages = frappe.get_all(
        "Funda Chat Message",
        filters={"session": session_name},
        fields=["role", "content", "creation"],
        order_by="creation asc"
    )
    return {"status": "success", "messages": messages}