# Makefile for managing Docker-based FastAPI app

up:
	docker compose up --build

down:
	docker compose down

bash:
	docker exec -it med_extractor_app bash

clean:
	docker system prune -a --volumes -f
