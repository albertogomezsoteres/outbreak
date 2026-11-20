# Isolated runtime for API experiments: agent-written scripts execute inside task workspaces, so
# running large experiments in a container is the recommended setup (docs/reproducibility.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends git make && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 runner
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -e ".[api,tracking]"
COPY . .
RUN chown -R runner:runner /app
USER runner

# docker run --rm -e OPENROUTER_API_KEY -v $PWD/outputs:/app/outputs outbreak:latest run experiments/...
ENTRYPOINT ["outbreak"]
CMD ["smoke"]
