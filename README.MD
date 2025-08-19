mkdir -p ./qdrant_data
docker run -p 6333:6333 \
    -v "$(pwd)/qdrant_data:/qdrant/storage" \
    qdrant/qdrant