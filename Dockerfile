FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV SAFEWHEELS_DB=/data/safewheels.sqlite
ENV PORT=4173

EXPOSE 4173
CMD ["python", "app.py"]
