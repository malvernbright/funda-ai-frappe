import os
import re
import ollama
import chromadb
from chromadb.config import Settings
import docx
import PyPDF2

# Get the directory where rag_engine.py is currently located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the vector_store relative to the base directory
# This will always work regardless of where 'funda_ai' is placed
CHROMA_PATH = os.path.join(BASE_DIR, "vector_store")

# Do the same for your knowledge base
DATA_PATH = os.path.join(BASE_DIR, "knowledge_base")


# Disable telemetry to stop the annoying terminal warning messages
chroma_client = chromadb.PersistentClient(
    path=CHROMA_PATH, 
    settings=Settings(anonymized_telemetry=False)
)
collection = chroma_client.get_or_create_collection(name="heritage_projects")


def get_local_embedding(text: str):
    """Safely fetch embeddings and catch any token limit errors."""
    try:
        response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
        return response["embedding"]
    except Exception as e:
        print(f"⚠️ Skipping chunk due to embedding error: {e}")
        return None

def extract_text_from_file(file_path: str) -> str:
    """Helper to route file parsing based on extension with crash protection."""
    try:
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            
        elif file_path.endswith(".pdf"):
            text = ""
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            return text
            
        elif file_path.endswith((".txt", ".md")):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        print(f"⚠️ Warning: Failed to read {os.path.basename(file_path)}. Skipping. Error: {e}")
        return ""
        
    return ""

def index_knowledge_base():
    id_counter = 0
    MAX_CHARS = 1000 # Lowered to 1000 just to be extra safe with token limits

    for root, _, files in os.walk(DATA_PATH):
        tier = "general"
        if "primary" in root: tier = "primary"
        elif "junior_high" in root: tier = "junior_high"
        elif "senior_high" in root: tier = "senior_high"

        for file in files:
            if file.endswith((".txt", ".md", ".docx", ".pdf")):
                file_path = os.path.join(root, file)
                content = extract_text_from_file(file_path)
                
                if not content: 
                    continue

                # THE FIX: Wipe out any line that is just a string of underscores
                content = re.sub(r'_{5,}', '', content)

                raw_paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 10]
                
                safe_chunks = []
                current_chunk = ""

                for paragraph in raw_paragraphs:
                    if len(current_chunk) + len(paragraph) < MAX_CHARS:
                        current_chunk += paragraph + "\n"
                    else:
                        if current_chunk:
                            safe_chunks.append(current_chunk.strip())
                        
                        if len(paragraph) > MAX_CHARS:
                            for i in range(0, len(paragraph), MAX_CHARS):
                                safe_chunks.append(paragraph[i:i+MAX_CHARS])
                            current_chunk = ""
                        else:
                            current_chunk = paragraph + "\n"
                
                if current_chunk:
                    safe_chunks.append(current_chunk.strip())

                for chunk in safe_chunks:
                    embedding = get_local_embedding(chunk)
                    
                    # Only save to the database if the embedding didn't crash
                    if embedding:
                        collection.upsert(
                            ids=[f"doc_{tier}_{id_counter}"],
                            embeddings=[embedding],
                            documents=[chunk],
                            metadatas=[{"source": file, "tier": tier}]
                        )
                        id_counter += 1
                    
    print(f"Successfully indexed/updated {id_counter} document segments.")


def query_local_rag(user_query: str, tier: str, num_results: int = 4):
    query_vector = get_local_embedding(user_query)
    
    # THE FIX: If the embedding failed and returned None, stop here and return empty context
    if not query_vector:
        return ""
    
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=num_results,
        where={"tier": tier} if tier != "all" else None
    )
    
    if results and results["documents"] and len(results["documents"][0]) > 0:
        return "\n---\n".join(results["documents"][0])
    return ""