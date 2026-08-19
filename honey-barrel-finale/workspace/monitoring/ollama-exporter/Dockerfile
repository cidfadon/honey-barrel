FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir prometheus_client requests
COPY exporter.py .
EXPOSE 9110
CMD ["python", "exporter.py"]
