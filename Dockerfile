FROM python:3.11.8-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código
COPY . .

# Ejecutar el bot
CMD ["python", "src/main.py"]
