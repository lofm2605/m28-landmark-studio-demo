FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Cổng lấy từ biến PORT của nơi lưu trữ (Render đặt PORT=10000); chạy cục bộ: docker run -e PORT=8000 -p 8000:8000 ...
CMD ["python", "demo_main.py"]
