FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Create upload directories
RUN mkdir -p uploads/questions uploads/practical_work

# Set environment variables
ENV FLASK_APP=/app/run.py
ENV FLASK_ENV=development
ENV PYTHONPATH=/app

EXPOSE 5000

# Run with python directly instead of flask run
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]
