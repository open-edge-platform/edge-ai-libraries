.SILENT: start down clean stop

start: 
	./update_dashboard.sh; \
	docker compose up -d;

down:
	docker compose down

clean:
	if [ -n "$$(docker ps -a -q)" ]; then \
		docker kill $$(docker ps -a -q); \
		docker rm $$(docker ps -a -q); \
	fi

stop: down clean