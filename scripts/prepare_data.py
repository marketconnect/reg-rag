import json
import re
import os

def clean_html(raw_html: str) -> str:
    """
    Удаляет HTML-теги из строки и нормализует пробелы.
    """
    # Удаляем HTML теги. [1, 2, 3, 4]
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    # Заменяем множественные пробелы на один и убираем пробелы по краям
    return " ".join(cleantext.split())

def prepare_data_for_hybrid_search(input_path: str, output_dir: str):
    """
    Обрабатывает JSON-файл с документом, очищает HTML, добавляет метаданные
    и подготавливает данные для гибридного поиска.
    """
    # Убедимся, что выходная директория существует
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(input_path, 'r', encoding='utf-8') as f:
        doc_data = json.load(f)

    doc_id = doc_data.get("id")
    documents_for_indexing = []

    for chapter in doc_data.get("chapters", []):
        chapter_id = chapter.get("id")
        for paragraph in chapter.get("paragraphs", []):
            paragraph_id = paragraph.get("id")
            raw_content = paragraph.get("content", "")

            if not raw_content:
                continue

            # 1. Очистка HTML-тегов
            cleaned_text = clean_html(raw_content)
            
            if not cleaned_text:
                continue

            # 2. Добавление метаинформации. [6, 13]
            document = {
                "text": cleaned_text,
                "metadata": {
                    "doc_id": doc_id,
                    "chapter_id": chapter_id,
                    "paragraph_id": paragraph_id
                }
            }
            documents_for_indexing.append(document)

    # 3. Сохранение подготовленных данных в файл.
    # Этот шаг имитирует подготовку данных для загрузки в поисковые системы (для BM25 и для эмбеддингов). [7, 8, 9]
    output_path = os.path.join(output_dir, f'doc_{doc_id}_prepared_for_search.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(documents_for_indexing, f, ensure_ascii=False, indent=2)

    print(f"Данные подготовлены и сохранены в {output_path}")
    print(f"Всего обработано параграфов: {len(documents_for_indexing)}")

if __name__ == "__main__":
    # Предполагается, что скрипт запускается из корневой папки проекта
    INPUT_FILE = "../raw_data/doc_3_processed.json"
    OUTPUT_DIR = "../data/prepared"
    
    prepare_data_for_hybrid_search(INPUT_FILE, OUTPUT_DIR)