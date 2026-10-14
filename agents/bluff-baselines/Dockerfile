FROM python:3.11-slim
ARG POLICY=heuristic
WORKDIR /app
LABEL org.triad-bluff.protocol="1.0" org.triad-bluff.runtime="2" \
      org.triad-bluff.cpu="1" org.triad-bluff.ram-bytes="268435456" \
      org.triad-bluff.scratch-bytes="67108864" \
      org.triad-bluff.gpu="false" org.triad-bluff.gpu-bytes="0"
COPY src/ ./src/
ENV BLUFF_POLICY=${POLICY} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 HOME=/tmp
USER 10000:10000
ENTRYPOINT ["python", "src/agent.py"]
