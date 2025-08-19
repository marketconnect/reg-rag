import json
import re
import os
import sqlite3
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

# --- Configuration ---
# Paths
SOURCE_DATA_DIR = "raw_data/"
DB_PATH = "data/storage/hybrid_search.db"
STORAGE_DIR = "data/storage"

# Qdrant
# Assuming Qdrant is running locally in a Docker container.
# docker run -p 6333:6333 qdrant/qdrant
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "legal_docs_hybrid"

# Embedding Model
# A lightweight model suitable for general purpose sentence embeddings.
MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2'


# --- Helper Functions ---

def clean_html(raw_html: str) -> str:
    """
    Removes HTML tags from a string and normalizes whitespace.
    """
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return " ".join(cleantext.split())

def prepare_documents_from_directory(source_dir: str) -> list:
    """
    Loads all source JSON files from a directory, cleans HTML, and structures data for indexing.
    """
    print(f"Loading and preparing data from directory: {source_dir}...")
    all_prepared_docs = []

    if not os.path.isdir(source_dir):
        print(f"Error: Source directory not found at {source_dir}")
        return all_prepared_docs

    for filename in sorted(os.listdir(source_dir)):
        if filename.endswith(".json"):
            file_path = os.path.join(source_dir, filename)
            print(f"  - Processing file: {filename}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    doc_data = json.load(f)

                doc_id = doc_data.get("id")

                for chapter in doc_data.get("chapters", []):
                    chapter_id = chapter.get("id")
                    for paragraph in chapter.get("paragraphs", []):
                        paragraph_id = paragraph.get("id")
                        content = paragraph.get("content", "")

                        # Пропускаем параграфы без контента
                        if not content:
                            continue

                        cleaned_text = clean_html(content)
                        
                        # ФИЛЬТРУЕМ МУСОР: Пропускаем слишком короткие или бессмысленные параграфы
                        # 30 символов - это примерный порог, его можно настроить.
                        if not cleaned_text or len(cleaned_text) < 30:
                            continue

                        all_prepared_docs.append({
                            "text": cleaned_text,
                            "metadata": {
                                "doc_id": doc_id,
                                "chapter_id": chapter_id,
                                "paragraph_id": paragraph_id
                            }
                        })
            except Exception as e:
                print(f"    Warning: An error occurred while processing {filename}: {e}. Skipping.")

    print(f"Prepared a total of {len(all_prepared_docs)} documents from all files.")
    return all_prepared_docs

def setup_sqlite(db_path: str):
    """
    Sets up the SQLite database with a documents table and an FTS5 virtual table
    for efficient full-text search, which serves the BM25 part of our search. [8, 12, 14]
    """
    print(f"Setting up SQLite database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Drop tables if they exist for a clean run
    cursor.execute('DROP TABLE IF EXISTS documents')
    cursor.execute('DROP TABLE IF EXISTS documents_fts')

    # Main table to store content and metadata
    cursor.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            doc_id INTEGER,
            chapter_id INTEGER,
            paragraph_id INTEGER
        )
    ''')

    # FTS5 virtual table for keyword search
    cursor.execute('''
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            text,
            content='documents',
            content_rowid='id'
        )
    ''')

    # Trigger to keep FTS table synchronized with the main documents table
    cursor.execute('''
        CREATE TRIGGER documents_after_insert AFTER INSERT ON documents
        BEGIN
            INSERT INTO documents_fts(rowid, text) VALUES (new.id, new.text);
        END;
    ''')
    conn.commit()
    return conn

def setup_qdrant(client: QdrantClient, collection_name: str, vector_size: int):
    """
    Ensures the Qdrant collection for vector storage is created with the correct configuration. [1, 2]
    """
    print(f"Setting up Qdrant collection: '{collection_name}'")
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )
    print("Qdrant collection created successfully.")

def main():
    """
    Main function to run the full data preparation and indexing pipeline.
    """
    # 0. Ensure storage directory exists
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR)

    # 1. Prepare data from source file
    documents = prepare_documents_from_directory(SOURCE_DATA_DIR)
    if not documents:
        print("No documents to index. Exiting.")
        return

    # 2. Initialize model, DB, and vector store clients
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME) # [3, 4, 6, 7]
    vector_size = model.get_sentence_embedding_dimension()

    sql_conn = setup_sqlite(DB_PATH)
    sql_cursor = sql_conn.cursor()

    qdrant_client = QdrantClient(url=QDRANT_URL) # [1, 5]
    setup_qdrant(qdrant_client, COLLECTION_NAME, vector_size)

    # 3. Generate embeddings for all documents
    print("Generating embeddings for all documents...")
    texts_to_embed = [doc['text'] for doc in documents]
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)

    # 4. Index data into SQLite and prepare points for Qdrant
    print("Indexing data into SQLite and preparing for Qdrant...")
    points_to_upsert = []
    for i, doc in enumerate(documents):
        # Insert into SQLite and get the auto-generated primary key
        sql_cursor.execute(
            "INSERT INTO documents (text, doc_id, chapter_id, paragraph_id) VALUES (?, ?, ?, ?)",
            (doc['text'], doc['metadata']['doc_id'], doc['metadata']['chapter_id'], doc['metadata']['paragraph_id'])
        )
        db_id = sql_cursor.lastrowid

        # Use the SQLite ID as the Qdrant point ID for a direct link
        points_to_upsert.append(
            models.PointStruct(
                id=db_id,
                vector=embeddings[i].tolist(),
                payload=doc['metadata']
            )
        )

    # 5. Batch upsert to Qdrant and commit to SQLite
    print(f"Upserting {len(points_to_upsert)} points to Qdrant...")
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points_to_upsert,
        wait=True
    )

    print("Committing changes to SQLite...")
    sql_conn.commit()
    sql_conn.close()

    print("\n--- Setup Complete ---")
    print(f"Data has been indexed into SQLite ({DB_PATH}) for keyword search.")
    print(f"Embeddings have been indexed into Qdrant (collection: '{COLLECTION_NAME}') for semantic search.")

if __name__ == "__main__":
    main()