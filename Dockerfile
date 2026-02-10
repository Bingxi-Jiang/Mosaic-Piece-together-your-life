FROM python:3.11-slim

WORKDIR /app

# system deps（按需加；如果你截图用到 pillow / quartz，不建议在 Linux 内截图）
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# copy project
COPY . /app

# env
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# 注意：生产环境不要 --reload
CMD ["uvicorn", "artified_backend.serve:app", "--host", "0.0.0.0", "--port", "8000"]
