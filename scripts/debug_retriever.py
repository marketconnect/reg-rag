# scripts/debug_retriever.py
import sqlite3
import sys

DB_PATH = "../data/storage/hybrid_search.db"

def debug_search(query: str, limit: int = 15):
    """
    Выполняет поиск FTS5 и извлекает полный текст найденных документов для анализа.
    """
    print(f"--- Поиск в SQLite FTS5 по запросу: '{query}' ---")
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Находим ID релевантных документов с помощью FTS
            cursor.execute(
                "SELECT rowid, rank FROM documents_fts WHERE text MATCH ? ORDER BY rank LIMIT ?",
                (query, limit)
            )
            fts_results = cursor.fetchall()
            
            if not fts_results:
                print("Поиск FTS не дал результатов.")
                return

            print(f"\nНайдено {len(fts_results)} совпадений в таблице FTS. Проверяем полный текст...\n")
            
            top_ids = [res['rowid'] for res in fts_results]
            
            # 2. Извлекаем полный текст для этих ID из основной таблицы
            placeholders = ','.join('?' for _ in top_ids)
            cursor.execute(
                f"SELECT id, doc_id, chapter_id, paragraph_id, text FROM documents WHERE id IN ({placeholders})",
                top_ids
            )
            
            # Создаем словарь для быстрого доступа к полному тексту
            full_docs_map = {row['id']: dict(row) for row in cursor.fetchall()}

            # 3. Выводим результаты в порядке релевантности FTS
            for res in fts_results:
                doc_id = res['rowid']
                rank = res['rank']
                full_doc = full_docs_map.get(doc_id)
                
                if full_doc:
                    print(f"ID: {full_doc['id']}, Doc ID: {full_doc['doc_id']}, Rank: {rank:.2f}")
                    print(f"Полный текст в базе: '{full_doc['text']}'")
                    print("-" * 20)
                
    except sqlite3.Error as e:
        print(f"Ошибка SQLite: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        search_query = " ".join(sys.argv[1:])
        debug_search(search_query)
    else:
        print("Ошибка: Укажите поисковый запрос в качестве аргумента.")
        print("Пример: python scripts/debug_retriever.py \"приказом Минтруда\"")