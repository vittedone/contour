FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py sources.py analysis.py reports.py demo.py demo_materials.json dispatch_analysis.py ./
COPY migrations migrations
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
