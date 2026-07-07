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
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --fix-missing \
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
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries && \
    apt-get update && apt-get install -y --no-install-recommends --fix-missing \
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

# Install all pip deps before git clone (cached even when repos update)
RUN /opt/mlpstorage-env/bin/pip install --upgrade pip --no-cache-dir \
    && /opt/mlpstorage-env/bin/pip install --no-cache-dir \
        numpy \
        pandas \
        "h5py>=3.11.0" \
        "mpi4py>=3.1.4" \
        "omegaconf>=2.2.0" \
        "hydra-core>=1.3.2" \
        "Pillow>=9.3.0" \
        PyYAML \
        "psutil>=5.9" \
        pyarrow \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu \
    && /opt/mlpstorage-env/bin/pip install --no-cache-dir tensorflow-cpu tfrecord \
    && printf '#!/opt/mlpstorage-env/bin/python\nfrom tfrecord.tools.tfrecord2idx import main\nmain()\n' \
       > /opt/mlpstorage-env/bin/tfrecord2idx \
    && chmod +x /opt/mlpstorage-env/bin/tfrecord2idx

# Clone repos (shallow clones to save space)
RUN git clone --depth 1 --branch v2.0 \
        https://github.com/mlcommons/storage.git /opt/mlpstorage-src \
    && git clone --depth 1 --branch mlperf_storage_v2.0 \
        https://github.com/argonne-lcf/dlio_benchmark.git /opt/dlio-src

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
RUN /opt/mlpstorage-env/bin/pip install --no-cache-dir --no-deps /opt/dlio-src \
    && /opt/mlpstorage-env/bin/pip install --no-cache-dir --no-deps /opt/mlpstorage-src \
    && rm -rf /opt/dlio-src/.git /opt/mlpstorage-src/.git

# Stage 2: Final image
FROM ubuntu:24.04

LABEL maintainer="DingoFS Team"
LABEL description="Storage performance testing tools: fio, vdbench, mdtest, pjdtest, LTP"
LABEL version="1.2"

ENV TZ=Asia/Shanghai
ENV PATH=/opt/vdbench:/opt/ltp:/opt/mlpstorage-env/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Layer 1: system packages + mdtest build + cleanup all in one layer
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --fix-missing \
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
    ln -sf /usr/lib/x86_64-linux-gnu/libjemalloc.so.2 /lib64/libjemalloc.so.2 && \
    cd /tmp && \
    git clone --depth 1 https://github.com/hpc/ior.git && \
    cd ior && \
    ./bootstrap && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/ior && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Layer 2: install vdbench
COPY vdbench50406.zip /tmp/vdbench.zip
RUN mkdir -p /opt/vdbench && \
    unzip -q /tmp/vdbench.zip -d /opt/vdbench/ && \
    chmod +x /opt/vdbench/vdbench && \
    rm -f /tmp/vdbench.zip

# Layer 3-6: copy heavy directories from builders (--chmod avoids duplicate layer)
COPY --from=ltp-builder --chmod=755 /opt/ltp /opt/ltp
COPY --from=mlperf-builder --chmod=755 /opt/mlpstorage-env /opt/mlpstorage-env
COPY --from=mlperf-builder --chmod=755 /opt/mlpstorage-src /opt/mlpstorage-src
COPY --from=mlperf-builder --chmod=755 /opt/dlio-src /opt/dlio-src

# Layer 7: install python deps (cached unless requirements.txt changes)
COPY dingofs-integration-test/requirements.txt /tmp/req.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/req.txt && \
    pip3 cache purge && \
    rm -f /tmp/req.txt

# Layer 8: copy project files (frequently-changing files go AFTER pip)
COPY --chmod=755 scripts/ /scripts/
COPY --chmod=755 scenarios/ /scenarios/
COPY pjdtest/ /pjdtest/
COPY --chmod=755 dingo /usr/local/bin/dingo
COPY --chmod=755 entrypoint.sh /entrypoint.sh
COPY --chmod=755 run_model.sh /usr/local/bin/run_model.sh
COPY dingofs-integration-test /dingofs-integration-test

# Layer 9: build pjdtest, set permissions
RUN chmod +x /scripts/generate_report.py /scripts/notify.sh \
        /usr/local/bin/dingo /usr/local/bin/run_model.sh /entrypoint.sh && \
    cd /pjdtest && \
    autoreconf -ifs && ./configure && make pjdfstest && rm -rf autom4te.cache && \
    cd /dingofs-integration-test && \
    chmod +x run_tests.py && \
    mkdir -p log && chmod 777 log && \
    chmod 777 /opt/ltp && \
    mkdir -p /opt/ltp/results /opt/ltp/output && \
    chmod 777 /opt/ltp/results /opt/ltp/output && \
    mkdir -p /custom && chmod 777 /custom/ && \
    chmod -R a+rX /pjdtest /dingofs-integration-test

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

# Prevent OpenBLAS from spawning one thread per CPU core
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1

# Set working directory for test operations
WORKDIR /data
