FROM python:3.12-slim

WORKDIR /app
COPY . .

ENV SAFEWHEELS_DB=/data/safewheels.sqlite
ENV PORT=4173

EXPOSE 4173
CMD ["python", "app.py"]
