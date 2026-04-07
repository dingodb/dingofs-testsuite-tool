#!/bin/bash
# Generator script for 96 fio scenarios
# 4 types x 2 direct x 3 bs x 4 numjobs = 96 files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR"

generate_fio_scenario() {
    local rw="$1"
    local direct="$2"
    local bs="$3"
    local numjobs="$4"
    local filename="$5"
    local is_random="$6"

    cat > "$SCENARIOS_DIR/$filename" << EOF
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

            generate_fio_scenario "randread" "$direct" "$bs" "$numjobs" "rand_read_$fname_base.fio" "true"
            generate_fio_scenario "randwrite" "$direct" "$bs" "$numjobs" "rand_write_$fname_base.fio" "true"
            generate_fio_scenario "read" "$direct" "$bs" "$numjobs" "seq_read_$fname_base.fio" "false"
            generate_fio_scenario "write" "$direct" "$bs" "$numjobs" "seq_write_$fname_base.fio" "false"
        done
    done
done

echo "Generated 96 fio scenario files in $SCENARIOS_DIR"
