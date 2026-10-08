FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY bloatdetective/ ./bloatdetective/
RUN pip install --no-cache-dir .
# Glama/Docker runners: server speaks MCP over stdio; DSN/DB are runtime env.
ENV BLOAT_DSN="dbname=bloatdemo user=postgres host=localhost port=5433" \
    BLOAT_DB="/data/timeline.db"
CMD ["bloat-mcp"]
