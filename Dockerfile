# DingoFS Storage Benchmark Tools
# A Docker image with fio, vdbench, mdtest, pjdtest, and LTP storage testing tools
# Base image: ubuntu:24.04 (per project requirement)

# Stage 1: Build LTP
FROM ubuntu:24.04 AS ltp-builder

LABEL maintainer="DingoFS Team"
LABEL description="LTP build stage"

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install LTP build dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        autoconf \
        automake \
        libtool \
        pkg-config \
        git \
        ca-certificates \
        bison \
        flex \
        libcap-dev \
        libnuma-dev \
        libpopt-dev \
        libssl-dev \
        uuid-dev \
        perl \
        libtimedate-perl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Configure git to use system CA certificates
RUN git config --global http.sslCAinfo /etc/ssl/certs/ca-certificates.crt

# Clone and build LTP (use 20240930 stable release - runltp still works)
RUN git clone --depth 1 --branch 20240930 https://github.com/linux-test-project/ltp.git /tmp/ltp && \
    cd /tmp/ltp && \
    make autotools && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/ltp

# Stage 2: Final image
FROM ubuntu:24.04

LABEL maintainer="DingoFS Team"
LABEL description="Storage performance testing tools: fio, vdbench, mdtest, pjdtest, LTP"
LABEL version="1.1"

ENV TZ=Asia/Shanghai
ENV PATH=/opt/vdbench:/opt/ltp:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install runtime dependencies only (no build tools)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fio \
        python3 \
        python3-pip \
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
        libaio-dev \
        perl \
        libtimedate-perl \
        vim \
        numactl \
        libjemalloc2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    # Create symlink for libjemalloc.so.2 at /lib64/ path used by dingofs tools
    ln -sf /usr/lib/x86_64-linux-gnu/libjemalloc.so.2 /lib64/libjemalloc.so.2

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

# Copy LTP from builder stage
COPY --from=ltp-builder /opt/ltp /opt/ltp

# Phase 3: Python and report generation scripts
RUN mkdir -p /scripts
COPY scripts/generate_report.py /scripts/generate_report.py
COPY scripts/notify.sh /scripts/notify.sh
RUN chmod +x /scripts/generate_report.py /scripts/notify.sh

# Phase 2: Copy scenario files
COPY scenarios/ /scenarios/

# Phase 5: Copy and build pjdtest tool
COPY pjdtest/ /pjdtest/
RUN cd /pjdtest && \
    autoreconf -ifs && \
    ./configure && \
    make pjdfstest && \
    rm -rf autom4te.cache

# Create custom config mount point
RUN mkdir -p /custom && chmod 777 /custom/

# Copy dingo CLI tool
COPY dingo /usr/local/bin/dingo
RUN chmod +x /usr/local/bin/dingo

# Copy dingo-client
COPY dingo-client /root/.dingo/components/dingo-client/main/dingo-client
RUN chmod +x /root/.dingo/components/dingo-client/main/dingo-client

# Copy dingo-cache
COPY dingo-cache /root/.dingo/components/dingo-cache/main/dingo-cache
RUN chmod +x /root/.dingo/components/dingo-cache/main/dingo-cache

# Copy dingofs-integration-test
COPY dingofs-integration-test /dingofs-integration-test
RUN cd /dingofs-integration-test && \
    pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    chmod +x run_tests.py

# Phase 2: Copy and set entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# Set working directory for test operations
WORKDIR /data
