# DingoFS Storage Benchmark Tools
# A Docker image with fio, vdbench, and mdtest storage testing tools
# Base image: ubuntu:24.04 (per project requirement)

FROM ubuntu:24.04

LABEL maintainer="DingoFS Team"
LABEL description="Storage performance testing tools: fio, vdbench, mdtest"
LABEL version="1.0"

# Set timezone to Asia/Shanghai
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set proxy for network access
ENV http_proxy=http://hproxy.it.zetyun.cn:1080
ENV https_proxy=http://hproxy.it.zetyun.cn:1080

# Install all tools and dependencies in a single layer to minimize image size
# - fio: Flexible I/O tester for storage performance benchmarks
# - default-jre-headless: Java runtime for vdbench (headless = no GUI deps)
# - mdtest: Metadata performance testing tool (built from IOR source)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fio \
        python3 \
        default-jre-headless \
        wget \
        unzip \
        ca-certificates \
        git \
        build-essential \
        libopenmpi-dev \
        openmpi-bin \
        autoconf \
        automake \
        libtool \
        pkg-config \
        libaio-dev && \
    # Clean apt cache to minimize image size (per D-06)
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy vdbench archive and install vdbench
COPY vdbench50406.zip /tmp/vdbench.zip
RUN mkdir -p /opt/vdbench && \
    unzip -q /tmp/vdbench.zip -d /opt/vdbench/ && \
    chmod +x /opt/vdbench/vdbench && \
    rm -f /tmp/vdbench.zip

# Build mdtest from source (part of IOR suite)
RUN cd /tmp && \
    git clone --depth 1 https://github.com/hpc/ior.git && \
    cd ior && \
    ./bootstrap && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/ior

# Phase 3: Python and report generation scripts
RUN mkdir -p /scripts
COPY scripts/generate_report.py /scripts/generate_report.py
RUN chmod +x /scripts/generate_report.py

# Phase 2: Copy scenario files
COPY scenarios/ /scenarios/

# Create custom config mount point
RUN mkdir -p /custom && chmod 777 /custom/

# Phase 2: Copy and set entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# Set working directory for test operations
WORKDIR /data
