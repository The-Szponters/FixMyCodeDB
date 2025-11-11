FROM mongo:6

RUN apt-get update && apt-get install -y \
    bash \
    curl \
    nano \
    vim \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Europe/Warsaw
RUN ln -sf /usr/share/zoneinfo/Europe/Warsaw /etc/localtime && dpkg-reconfigure -f noninteractive tzdata

COPY mongo-init.js /docker-entrypoint-initdb.d/
