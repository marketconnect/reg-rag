import os
import sqlite3
import re
from typing import List, Dict, Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# --- Configuration ---
# Resolve project root relative to this file
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)

DB_PATH = os.path.join(_PROJECT_ROOT, "data", "storage", "hybrid_search.db")
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "legal_docs_hybrid"
# ЗАМЕНА МОДЕЛИ: Используем более мощную многоязычную модель для лучшего понимания русского языка.
MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2'
TOP_K = 5

def _sanitize_fts_query(query: str) -> str:
    """Удаляет или экранирует спецсимволы, которые могут сломать FTS5 MATCH query."""
    return re.sub(r'[^\w\s]', ' ', query)

class HybridRetriever:
    """
    A retriever that combines keyword-based (BM25-like) and vector-based search
    to find the most relevant documents.
    """
    def __init__(self, db_path, qdrant_url, collection_name, model_name):
        self.db_path = db_path
        self.qdrant_client = QdrantClient(url=qdrant_url)
        self.model = SentenceTransformer(model_name)
        self.collection_name = collection_name

    def _search_sqlite(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Performs a full-text search in SQLite using FTS5."""
        try:
            # ИСПРАВЛЕНИЕ ОШИБКИ: Очищаем запрос перед передачей в FTS5
            sanitized_query = _sanitize_fts_query(query)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT rowid, rank FROM documents_fts WHERE text MATCH ? ORDER BY rank LIMIT ?",
                    (sanitized_query, k)
                )
                return [{"id": row[0], "score": row[1]} for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"SQLite search error: {e}")
            return []

    def _search_qdrant(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Performs a semantic vector search in Qdrant."""
        try:
            query_vector = self.model.encode(query).tolist()
            search_result = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k
            )
            return [{"id": point.id, "score": point.score} for point in search_result]
        except Exception as e:
            print(f"Qdrant search error: {e}")
            return []

    def _reciprocal_rank_fusion(self, results_lists: List[List[Dict[str, Any]]], k_rrf: int = 60) -> List[Dict[str, Any]]:
        """Combines search results using Reciprocal Rank Fusion."""
        fused_scores = {}
        for results in results_lists:
            for rank, doc in enumerate(results):
                doc_id = doc['id']
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = 0
                fused_scores[doc_id] += 1 / (k_rrf + rank + 1)

        reranked_results = [
            {"id": doc_id, "score": score}
            for doc_id, score in sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
        ]
        return reranked_results

    def retrieve(self, query: str, k: int) -> List[Dict[str, Any]]:
        """
        Executes the hybrid search pipeline and returns the top k results with their full data.
        """
        sqlite_results = self._search_sqlite(query, k)
        qdrant_results = self._search_qdrant(query, k)
        fused_results = self._reciprocal_rank_fusion([sqlite_results, qdrant_results])
        
        if not fused_results:
            return []

        top_ids = [result['id'] for result in fused_results[:k]]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in top_ids)
            cursor.execute(
                f"SELECT id, doc_id, chapter_id, paragraph_id, text FROM documents WHERE id IN ({placeholders})",
                top_ids
            )
            results_map = {row['id']: dict(row) for row in cursor.fetchall()}
            ordered_docs = [results_map[doc_id] for doc_id in top_ids if doc_id in results_map]

        return ordered_docs

# Initialize the retriever once to be used by the tool
retriever = HybridRetriever(DB_PATH, QDRANT_URL, COLLECTION_NAME, MODEL_NAME)

@tool
def hybrid_search(query: str) -> str:
    """
    Searches for relevant paragraphs in legal documents using a hybrid search approach.
    Use this tool to find specific regulations, rules, or answers to questions
    about operational procedures. Input should be a concise question or search query.
    """
    print(f"Tool 'hybrid_search' called with query: '{query}'")
    documents = retriever.retrieve(query, k=TOP_K)
    if not documents:
        return "No relevant documents found for this query."
    
    formatted_results = []
    for doc in documents:
        formatted_results.append(
            f"Source (doc_id: {doc['doc_id']}, chapter_id: {doc['chapter_id']}, paragraph_id: {doc['paragraph_id']}):\n"
            f"Content: {doc['text']}\n"
        )
    return "\n---\n".join(formatted_results)

def create_agent():
    """Creates and configures the ReAct agent."""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not found in .env file. Please add it.")

    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0)
    tools = [hybrid_search]

    prompt_template = """
    You are a meticulous legal assistant. Your goal is to find the single, exact paragraph in the provided legal documents that justifies why a given answer is correct for a given question.

    You will be given a Question and the Correct Answer. You must find the document paragraph that contains the rule or regulation proving the answer is correct.

    Follow these steps:
    1. Analyze the user's Question and the provided Correct Answer. Formulate a precise search query that combines keywords from both to find the justifying text. For example, if the question is about "who can perform an inspection" and the answer is "an operator with group III", your search query should contain terms like "единоличный осмотр", "оперативный персонал", and "группа III".
    2. Use the 'hybrid_search' tool with your query.
    3. Examine the search results. The results will contain the text of the paragraph and its location (doc_id, chapter_id, paragraph_id).
    4. Compare the content of each result paragraph with the Question and Correct Answer. The correct paragraph must directly support the answer.
    5. If the results are not relevant enough or do not contain the justification, refine your search query based on what you've learned and go back to step 2. Try to be more specific or use different keywords.
    6. Repeat this process until you are confident you have found the correct paragraph that justifies the answer.
    7. If after several attempts you cannot find a paragraph that directly justifies the answer, you MUST stop and return a JSON object indicating failure.
    8. Once you have found the correct paragraph, your FINAL ANSWER MUST be ONLY a single JSON object containing the location of that paragraph.

    Example Final Answer Format:
    ```json
    {{
      "doc_id": 9,
      "chapter_id": 5,
      "paragraph_id": 434408
    }}
    ```

    Example Final Answer on Failure:
    ```json
    {{
      "error": "Justification paragraph not found after multiple attempts."
    }}
    ```

    Do not add any other text, explanation, or markdown formatting around your final answer.

    TOOLS:
    ------
    You have access to the following tools: {tools}

    To use a tool, please use the following format:
    ```
    Thought: Do I need to use a tool? Yes
    Action: The action to take. Should be one of [{tool_names}]
    Action Input: The input to the action
    Observation: The result of the action
    ```

    When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:
    ```
    Thought: Do I need to use a tool? No
    Final Answer: your final answer in the specified JSON format
    ```

    Begin!

    Here is the task:
    {input}
    {agent_scratchpad}
    """

    prompt = PromptTemplate.from_template(prompt_template)
    agent = create_react_agent(llm, tools, prompt)
    
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=5,
        handle_parsing_errors=True
    )
    return agent_executor 