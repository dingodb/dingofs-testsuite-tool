#!/bin/bash
# Generator script for fio scenarios with small block sizes
# 4 types x 2 direct x 7 bs x 4 numjobs = 224 files
# Output: scenarios/fio_small/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/fio_small"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Remove old scenario files
rm -f "$OUTPUT_DIR"/*.fio

generate_fio_scenario() {
    local rw="$1"
    local direct="$2"
    local bs="$3"
    local numjobs="$4"
    local filename="$5"
    local is_random="$6"

    cat > "$OUTPUT_DIR/$filename" << EOF
[global]
rw=$rw
bs=$bs
direct=$direct
numjobs=$numjobs
ioengine=libaio
iodepth=1
runtime=60
time_based=1
directory=/data
size=8G
group_reporting=1
EOF

    if [ "$is_random" = "true" ]; then
        echo "norandommap=1" >> "$OUTPUT_DIR/$filename"
    fi

    echo "" >> "$OUTPUT_DIR/$filename"
    echo "[job1]" >> "$OUTPUT_DIR/$filename"
}

# Generate all 224 scenarios (4 types x 2 direct x 7 bs x 4 numjobs)
for direct in 0 1; do
    for bs in 128 256 512 1k 2k 4k 8k; do
        for numjobs in 1 8 16 32; do
            fname_base="${direct}d_${bs}_${numjobs}j"

            generate_fio_scenario "randread" "$direct" "$bs" "$numjobs" "rand_read_$fname_base.fio" "true"
            generate_fio_scenario "randwrite" "$direct" "$bs" "$numjobs" "rand_write_$fname_base.fio" "true"
            generate_fio_scenario "read" "$direct" "$bs" "$numjobs" "seq_read_$fname_base.fio" "false"
            generate_fio_scenario "write" "$direct" "$bs" "$numjobs" "seq_write_$fname_base.fio" "false"
        done
    done
done

count=$(ls "$OUTPUT_DIR"/*.fio 2>/dev/null | wc -l)
echo "Generated $count fio scenario files in $OUTPUT_DIR"
