import os
import re
import ollama
import chromadb
from chromadb.config import Settings
import docx
import PyPDF2
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "vector_store")
DATA_PATH = os.path.join(BASE_DIR, "knowledge_base")

chroma_client = chromadb.PersistentClient(
    path=CHROMA_PATH, 
    settings=Settings(anonymized_telemetry=False)
)
collection = chroma_client.get_or_create_collection(name="heritage_projects")

def get_local_embedding(text: str):
    """Encodes text passages into stable vector tensors."""
    try:
        response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
        return response["embedding"]
    except Exception as e:
        logger.error(f"Embedding chunk processing error: {e}")
        return None

def extract_text_from_file(file_path: str) -> str:
    """Robust cross-platform reader script wrapper for unstructured formats."""
    try:
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
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
        logger.warning(f"File extraction failure on item {os.path.basename(file_path)}: {e}")
    return ""

def index_knowledge_base():
    """Walks the folder hierarchies relative to database root directories, building isolated metadata scopes."""
    id_counter = 0
    MAX_CHARS = 1000

    # Ensure root path framework structures are created cleanly
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)
        logger.info(f"Created knowledge base directory wrapper at {DATA_PATH}. Place your folders here.")
        return

    for root, _, files in os.walk(DATA_PATH):
        # Determine current structural layer using dynamic relative path evaluations
        rel_path = os.path.relpath(root, DATA_PATH)
        path_parts = rel_path.split(os.sep)
        
        # Defaults to general/global mapping if file sits at top level root
        tier = path_parts[0] if (len(path_parts) >= 1 and path_parts[0] != ".") else "all"
        subject = path_parts[1] if len(path_parts) >= 2 else "general"

        for file in files:
            if file.endswith((".txt", ".md", ".docx", ".pdf")):
                file_path = os.path.join(root, file)
                content = extract_text_from_file(file_path)
                
                if not content.strip(): 
                    continue

                # Strip out long format line strings and separator characters
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
                    if embedding:
                        collection.upsert(
                            ids=[f"doc_{tier}_{subject}_{id_counter}"],
                            embeddings=[embedding],
                            documents=[chunk],
                            metadatas=[{"source": file, "tier": tier, "subject": subject}]
                        )
                        id_counter += 1
                        
    logger.info(f"Database generation script completed. Successfully mapped {id_counter} chunks.")

def query_local_rag(user_query: str, tier: str, subject: str, num_results: int = 4):
    """Executes multi-conditional metadata logic matrices directly across local store tables."""
    query_vector = get_local_embedding(user_query)
    if not query_vector:
        return ""
    
    # 8. Build a Boolean query syntax map for ChromaDB metadata validation
    conditions = []
    if tier and tier != "all" and tier != "all_levels":
        conditions.append({"tier": tier})
    if subject and subject != "general":
        conditions.append({"subject": subject})
        
    if len(conditions) == 1:
        where_clause = conditions[0]
    elif len(conditions) > 1:
        where_clause = {"$and": conditions}
    else:
        where_clause = None

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=num_results,
        where=where_clause
    )
    
    if results and results["documents"] and len(results["documents"][0]) > 0:
        return "\n---\n".join(results["documents"][0])
    return ""