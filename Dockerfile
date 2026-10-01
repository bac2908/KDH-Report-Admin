FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY kdh ./kdh
COPY templates ./templates
COPY static ./static
COPY run.py .
RUN useradd --uid 10001 --create-home kdh && mkdir -p /app/instance && chown -R kdh:kdh /app
USER kdh
ENV HOST=0.0.0.0 PORT=8090 PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["python", "run.py"]
