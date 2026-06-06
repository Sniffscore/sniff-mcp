FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir . boto3 uvicorn
ENV PORT=8080 SNIFF_DATA=/data SNIFF_ROLE=mcp
VOLUME ["/data"]
EXPOSE 8080
ENTRYPOINT ["/app/docker/entrypoint.sh"]
