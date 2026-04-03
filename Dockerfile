# DingoFS Storage Benchmark Tools
# A Docker image with fio, vdbench, and mdtest storage testing tools
# Base image: ubuntu:24.04 (per project requirement)

FROM ubuntu:24.04

LABEL maintainer="DingoFS Team"
LABEL description="Storage performance testing tools: fio, vdbench, mdtest"
LABEL version="1.0"

# Install all tools and dependencies in a single layer to minimize image size
# - fio: Flexible I/O tester for storage performance benchmarks
# - default-jre-headless: Java runtime for vdbench (headless = no GUI deps)
# - mdtest: Metadata performance testing tool (built from IOR source)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fio \
        default-jre-headless \
        wget \
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
    # Create vdbench directory
    mkdir -p /opt/vdbench && \
    # vdbench requires Oracle license acceptance - create instructions
    echo "vdbench download requires Oracle license acceptance" > /opt/vdbench/DOWNLOAD_INSTRUCTIONS.txt && \
    echo "Download vdbench50407.zip from Oracle and place vdbench.jar in /opt/vdbench/" >> /opt/vdbench/DOWNLOAD_INSTRUCTIONS.txt && \
    # Build mdtest from source (part of IOR suite)
    cd /tmp && \
    git clone --depth 1 https://github.com/hpc/ior.git && \
    cd ior && \
    ./bootstrap && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    # Clean up build artifacts
    rm -rf /tmp/ior && \
    # Clean apt cache to minimize image size (per D-06)
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory for test operations
WORKDIR /data

# Default command - interactive bash shell
CMD ["/bin/bash"]
