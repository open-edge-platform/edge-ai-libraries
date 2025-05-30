CONTAINER_IDS=$(docker ps -a --filter "ancestor=retriever-milvus" -q)

# Check if any containers were found
if [ -z "$CONTAINER_IDS" ]; then
  echo "No containers found"
  exit 0
fi

CONTAINER_IDS=($CONTAINER_IDS)
NUM_CONTAINERS=${#CONTAINER_IDS[@]}

for file in test_*.py; do
  docker cp "$file" ${CONTAINER_IDS[0]}:/home/user/retriever/src
done

for test_file in test_*.py; do
  docker exec -it ${CONTAINER_IDS[0]} bash -c "cd /home/user/retriever/src && python -m pytest $test_file_name --tb=short"
done
