import logging

import frappe
import json
import ollama
# from funda_ai.funda_ai.rag.rag_engine import query_local_rag
from .rag_engine import query_local_rag


SYSTEM_PROMPT = """
You are 'Funda', an encouraging Zimbabwean teacher assisting a student with their Heritage-Based Curriculum (HBC) project. 
You must NEVER write the project, generate the 6 stages, or give direct answers. 

Your goal is to use the Socratic method. 
1. Review the provided context from the official syllabus.
2. Ask a single, guiding question to help the student think critically about their local environment. 

If the student asks you to do the work, politely decline and ask them a question to get them started.
"""

@frappe.whitelist()
def chat_with_funda(message, tier="all", history="[]"):
    """
    Frappe API endpoint replacing the FastAPI chat route.
    """
    try:
        # 1. Parse history
        chat_history = json.loads(history)
        
        # 2. Query your local ChromaDB
        rag_context = query_local_rag(message, tier)
        
        # 3. Build Socratic prompt with context
        augmented_prompt = f"""
        Context from HBC Syllabus:
        {rag_context if rag_context else "No specific syllabus context found for this query."}
        
        Student's Question: {message}
        """
        
        # 4. Construct messages array for Ollama
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": augmented_prompt})
        
        # 5. Call local Ollama model (e.g., Llama 3 8B quantized)
        response = ollama.chat(
            model="qwen2.5-coder:7b", # Or whichever lightweight model you are targeting
            messages=messages
        )
        
        ai_reply = response['message']['content']
        
        # 6. Optional: Log the interaction to your custom Tutor Analytics Doctype
        frappe.get_doc({
            "doctype": "Tutor Analytics Log",
            "student": frappe.session.user,
            "query": message,
            "tier": tier
        }).insert(ignore_permissions=True)
        
        return {"status": "success", "reply": ai_reply}

    except Exception as e:
        logging.error(f"Funda AI Error: {str(e)}")
        frappe.log_error(f"Funda AI Error: {str(e)}", "Funda AI Chat Endpoint")
        return {"status": "error", "message": "Funda is currently taking a break. Please try again."}