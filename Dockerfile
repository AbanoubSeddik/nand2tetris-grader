FROM eclipse-temurin:21-jre AS java

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    && rm -rf /var/lib/apt/lists/*

COPY --from=java /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="$JAVA_HOME/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py .
COPY moodle_client.py .
COPY grading_engine.py .
COPY ai_report.py .
COPY database.py .
COPY bot.py .

COPY tools/ ./tools/
COPY grader_test_files/ ./grader_test_files/

RUN find tools/ -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
RUN java -version

VOLUME ["/app/data"]

CMD ["python", "bot.py"]