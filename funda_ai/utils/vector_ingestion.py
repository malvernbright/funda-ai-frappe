import os
import PyPDF2
import docx
import ollama
import chromadb
import frappe
from chromadb.config import Settings

def get_chroma_collection():
    """Initializes and returns the ChromaDB collection suitable for edge deployment."""
    # Store the vector database inside the Frappe site's private directory
    site_path = frappe.get_site_path()
    chroma_path = os.path.join(site_path, "private", "vector_store")
    
    chroma_client = chromadb.PersistentClient(
        path=chroma_path, 
        settings=Settings(anonymized_telemetry=False)
    )
    return chroma_client.get_or_create_collection(name="heritage_projects")

def get_local_embedding(text: str):
    """Safely fetch embeddings from the local Ollama instance."""
    try:
        response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
        return response["embedding"]
    except Exception as e:
        frappe.log_error(f"Ollama Embedding Error: {str(e)}", "Funda AI Ingestion")
        return None

def extract_text(file_path: str):
    """Parses text from PDF or DOCX files."""
    text = ""
    if file_path.endswith(".pdf"):
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    elif file_path.endswith(".docx"):
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    return text

def process_curriculum_file(doc_name: str, file_url: str, tier: str):
    """
    The main background job executed by Frappe RQ Workers.
    """
    try:
        # 1. Resolve the absolute file path on the server
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found on server: {file_path}")

        # 2. Extract Text
        raw_text = extract_text(file_path)
        if not raw_text:
            raise ValueError("No text could be extracted from the file. It may be scanned images.")

        # 3. Naive Chunking Strategy (Split by paragraphs to maintain context)
        paragraphs = raw_text.split("\n\n")
        safe_chunks = []
        current_chunk = ""
        
        # Group short paragraphs together to form meaningful semantic chunks (approx 300-500 words)
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            if len(current_chunk) + len(para) > 2000:
                safe_chunks.append(current_chunk.strip())
                current_chunk = para + "\n"
            else:
                current_chunk += para + "\n"
                
        if current_chunk:
            safe_chunks.append(current_chunk.strip())

        # 4. Generate Embeddings and Push to ChromaDB
        collection = get_chroma_collection()
        chunk_count = 0
        
        for index, chunk in enumerate(safe_chunks):
            embedding = get_local_embedding(chunk)
            
            if embedding:
                # Generate a unique ID for ChromaDB
                chunk_id = f"doc_{doc_name}_chunk_{index}"
                
                collection.upsert(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"source_doc": doc_name, "tier": tier}]
                )
                chunk_count += 1

        # 5. Update the Frappe Document with Success Metrics
        frappe.db.set_value("Curriculum Material", doc_name, {
            "indexing_status": "Indexed",
            "chunk_count": chunk_count,
            "error_log": f"Successfully indexed {chunk_count} chunks at {frappe.utils.now()}"
        })
        frappe.db.commit()

    except Exception as e:
        # 6. Graceful Error Handling: Update Frappe Doc so the user knows it failed
        error_msg = str(e)
        frappe.db.set_value("Curriculum Material", doc_name, {
            "indexing_status": "Failed",
            "error_log": error_msg
        })
        frappe.db.commit()
        frappe.log_error(title=f"Funda AI Ingestion Failed: {doc_name}", message=frappe.get_traceback())