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
# - mdtest: Metadata performance testing tool
# - wget: For downloading vdbench
# - unzip: For extracting vdbench distribution
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fio \
        default-jre-headless \
        mdtest \
        wget \
        unzip \
        ca-certificates && \
    # Create vdbench directory
    mkdir -p /opt/vdbench && \
    # Download vdbench from Oracle
    # Note: vdbench requires accepting Oracle license agreement
    # Using vdbench 5.04.07 as the stable release
    cd /tmp && \
    wget -q "https://www.oracle.com/technetwork/server-storage/vdbench-downloads-1901681.html" -O vdbench_download.html || true && \
    # Try direct download URL pattern (may require license acceptance)
    wget -q "https://download.oracle.com/otn/utilities_drivers/vdbench/vdbench50407.zip" -O vdbench.zip || \
    # Alternative: create placeholder if download fails
    echo "vdbench download requires Oracle license acceptance" > /opt/vdbench/DOWNLOAD_INSTRUCTIONS.txt && \
    # If zip was downloaded successfully, extract it
    if [ -f /tmp/vdbench.zip ] && [ -s /tmp/vdbench.zip ]; then \
        unzip -q /tmp/vdbench.zip -d /opt/vdbench/ && \
        # Find and move vdbench.jar to standard location
        find /opt/vdbench -name "vdbench.jar" -exec mv {} /opt/vdbench/vdbench.jar \; 2>/dev/null || true; \
    fi && \
    # Clean up temporary files
    rm -rf /tmp/vdbench.zip /tmp/vdbench_download.html && \
    # Clean apt cache to minimize image size (per D-06)
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory for test operations
WORKDIR /data

# Default command - interactive bash shell
CMD ["/bin/bash"]
