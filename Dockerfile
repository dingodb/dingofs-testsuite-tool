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

# Stage 1b: Build mlperf-storage Python environment
FROM ubuntu:24.04 AS mlperf-builder

ENV DEBIAN_FRONTEND=noninteractive

# Install mlperf build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3-pip \
        python3-venv \
        python3.12-dev \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create Python 3.12 venv
RUN python3.12 -m venv /opt/mlpstorage-env

# Clone repos (shallow clones to save space)
RUN git clone --depth 1 --branch v2.0 \
        https://github.com/mlcommons/storage.git /opt/mlpstorage-src \
    && git clone --depth 1 --branch mlperf_storage_v2.0 \
        https://github.com/argonne-lcf/dlio_benchmark.git /opt/dlio-src

# Install lightweight runtime dependencies
RUN /opt/mlpstorage-env/bin/pip install --upgrade pip \
    && /opt/mlpstorage-env/bin/pip install \
        numpy \
        pandas \
        "h5py>=3.11.0" \
        "mpi4py>=3.1.4" \
        "omegaconf>=2.2.0" \
        "hydra-core>=1.3.2" \
        "Pillow>=9.3.0" \
        PyYAML \
        "psutil>=5.9" \
        pyarrow

# Install CPU-only PyTorch + torchvision (~200MB vs ~2.5GB CUDA)
RUN /opt/mlpstorage-env/bin/pip install \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu

# Install CPU TensorFlow + tfrecord (~400MB vs 1+GB GPU)
RUN /opt/mlpstorage-env/bin/pip install tensorflow-cpu tfrecord \
    && printf '#!/opt/mlpstorage-env/bin/python\nfrom tfrecord.tools.tfrecord2idx import main\nmain()\n' \
       > /opt/mlpstorage-env/bin/tfrecord2idx \
    && chmod +x /opt/mlpstorage-env/bin/tfrecord2idx

# Patch dlio_benchmark for optional dependency guards
RUN sed -i \
      's/^import tensorflow as tf$/try:\n    import tensorflow as tf\nexcept ImportError:\n    tf = None/' \
      /opt/dlio-src/dlio_benchmark/profiler/tf_profiler.py \
    && sed -i \
      's/^from dlio_benchmark\.profiler\.tf_profiler import TFProfiler$/try:\n    from dlio_benchmark.profiler.tf_profiler import TFProfiler\nexcept (ImportError, Exception):\n    TFProfiler = None/' \
      /opt/dlio-src/dlio_benchmark/profiler/profiler_factory.py \
    && sed -i \
      's/^import tensorflow_io as tfio$/try:\n    import tensorflow_io as tfio\nexcept ImportError:\n    tfio = None/' \
      /opt/dlio-src/dlio_benchmark/framework/tf_framework.py

# Install dlio-benchmark and mlpstorage without pulling their deps
RUN /opt/mlpstorage-env/bin/pip install --no-deps /opt/dlio-src \
    && /opt/mlpstorage-env/bin/pip install --no-deps /opt/mlpstorage-src \
    && rm -rf /opt/dlio-src/.git /opt/mlpstorage-src/.git

# Stage 2: Final image
FROM ubuntu:24.04

LABEL maintainer="DingoFS Team"
LABEL description="Storage performance testing tools: fio, vdbench, mdtest, pjdtest, LTP"
LABEL version="1.1"

ENV TZ=Asia/Shanghai
ENV PATH=/opt/vdbench:/opt/ltp:/opt/mlpstorage-env/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install runtime dependencies only (no build tools)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fio \
        python3 \
        python3-pip \
        python3.12-venv \
        default-jre-headless \
        wget \
        curl \
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
        procps \
        bc \
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

# Copy mlperf-storage from builder stage
COPY --from=mlperf-builder /opt/mlpstorage-env /opt/mlpstorage-env
COPY --from=mlperf-builder /opt/mlpstorage-src /opt/mlpstorage-src
COPY --from=mlperf-builder /opt/dlio-src /opt/dlio-src

# Phase 3: Python and report generation scripts
RUN mkdir -p /scripts
COPY scripts/generate_report.py /scripts/generate_report.py
COPY scripts/notify.sh /scripts/notify.sh
RUN chmod +x /scripts/generate_report.py /scripts/notify.sh

# Phase 2: Copy scenario files (includes fio and fio_small directories)
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

# Copy dingofs-integration-test
COPY dingofs-integration-test /dingofs-integration-test
RUN cd /dingofs-integration-test && \
    pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    chmod +x run_tests.py && \
    mkdir -p log && chmod 777 log && \
    chmod 777 /opt/ltp && \
    mkdir -p /opt/ltp/results /opt/ltp/output && \
    chmod 777 /opt/ltp/results /opt/ltp/output

# Phase 2: Copy and set entrypoint
COPY entrypoint.sh /entrypoint.sh

# Copy mlperf run_model.sh
COPY run_model.sh /usr/local/bin/run_model.sh
RUN chmod +x /usr/local/bin/run_model.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# Prevent OpenBLAS from spawning one thread per CPU core
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1

# Set working directory for test operations
WORKDIR /data
