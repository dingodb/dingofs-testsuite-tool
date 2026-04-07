#!/bin/bash
# Generator script for 96 fio scenarios
# 4 types x 2 direct x 3 bs x 4 numjobs = 96 files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR"

generate_fio_scenario() {
    local name="$1"
    local rw="$2"
    local direct="$3"
    local bs="$4"
    local numjobs="$5"
    local filename="$6"
    local is_random="$7"

    cat > "$SCENARIOS_DIR/$filename" << EOF
[global]
name=$name
description=$name - direct=$direct bs=$bs numjobs=$numjobs
rw=$rw
bs=$bs
ioengine=libaio
iodepth=1
direct=$direct
numjobs=$numjobs
runtime=60
time_based=1
directory=/data
size=1G
group_reporting=1
EOF

    if [ "$is_random" = "true" ]; then
        echo "norandommap=1" >> "$SCENARIOS_DIR/$filename"
    fi

    echo "" >> "$SCENARIOS_DIR/$filename"
    echo "[job1]" >> "$SCENARIOS_DIR/$filename"
}

# Generate all 96 scenarios
for direct in 0 1; do
    for bs in 128k 1m 4m; do
        for numjobs in 1 8 16 32; do
            fname_base="${direct}d_${bs}_${numjobs}j"

            generate_fio_scenario "rand_read_$fname_base" "randread" "$direct" "$bs" "$numjobs" "rand_read_$fname_base.fio" "true"
            generate_fio_scenario "rand_write_$fname_base" "randwrite" "$direct" "$bs" "$numjobs" "rand_write_$fname_base.fio" "true"
            generate_fio_scenario "seq_read_$fname_base" "read" "$direct" "$bs" "$numjobs" "seq_read_$fname_base.fio" "false"
            generate_fio_scenario "seq_write_$fname_base" "write" "$direct" "$bs" "$numjobs" "seq_write_$fname_base.fio" "false"
        done
    done
done

echo "Generated 96 fio scenario files in $SCENARIOS_DIR"
