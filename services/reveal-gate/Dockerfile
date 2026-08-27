FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY reveal.py .
RUN useradd --system --no-create-home app
USER app
CMD ["python", "reveal.py"]
