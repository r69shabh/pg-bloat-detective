FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY bloatdetective/ ./bloatdetective/
RUN pip install --no-cache-dir .
# Glama/Docker runners: server speaks MCP over stdio; DSN/DB are runtime env.
# BLOAT_DB default is a relative path so missing /data never crashes startup.
ENV BLOAT_DSN="dbname=bloatdemo user=postgres host=localhost port=5433" \
    BLOAT_DB="timeline.db"
CMD ["bloat-mcp"]
