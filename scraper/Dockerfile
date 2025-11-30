FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y \
    bash \
    curl \
    nano \
    vim \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Europe/Warsaw
RUN ln -sf /usr/share/zoneinfo/Europe/Warsaw /etc/localtime && dpkg-reconfigure -f noninteractive tzdata

COPY . ./scraper
CMD ["python3", "-m", "scraper.main"]
