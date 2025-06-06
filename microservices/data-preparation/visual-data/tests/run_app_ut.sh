CONTAINER_IDS=$(docker ps -a --filter "ancestor=dataprep-visualdata-milvus" -q)

# Check if any containers were found
if [ -z "$CONTAINER_IDS" ]; then
  echo "No containers found"
  exit 0
fi

CONTAINER_IDS=($CONTAINER_IDS)
NUM_CONTAINERS=${#CONTAINER_IDS[@]}

for file in test_*.py; do
  docker cp "$file" ${CONTAINER_IDS[0]}:/home/user/dataprep/src
done

for test_file in test_*.py; do
  docker exec -it ${CONTAINER_IDS[0]} bash -c "cd /home/user/dataprep/src && python -m pytest $test_file --tb=short"
done
