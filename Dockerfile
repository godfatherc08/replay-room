# The live backend (python -m replay_room.api) for Azure Container Apps: the engine, its MCP server and the agents.
# Foundry is reached with the container app's managed identity (DefaultAzureCredential); no keys in the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Editable install: the engine finds data/ (models, fixtures) relative to its source tree.
COPY pyproject.toml requirements-ci.txt ./
COPY src ./src
RUN pip install -e ".[foundry]" -c requirements-ci.txt

COPY data/models ./data/models
COPY data/schema ./data/schema
COPY data/fixtures/synthetic_match_02 ./data/fixtures/synthetic_match_02

RUN useradd --create-home app && chown -R app /app/data
USER app
EXPOSE 8000
CMD ["python", "-m", "replay_room.api", "--host", "0.0.0.0", "--port", "8000"]
