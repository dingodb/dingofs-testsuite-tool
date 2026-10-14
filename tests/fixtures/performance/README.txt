These are actual local benchmark outputs captured on 2026-10-05.
Tools: /usr/bin/fio (fio-3.35) and elbencho 3.0-37.
Only absolute temporary paths were replaced with /tmp/dtt-perf-contract-example.
Each phase transferred 524288 bytes (four 128KiB files, two workers, 4KiB blocks).
No network or cluster workload was run.

elbencho common arguments:
-t 2 -s 131072 -b 4096 --direct --lat --nolive
--jsonfile RESULT /tmp/dtt-perf-contract-example/el-file[0-3]
seq-write: -w
seq-read: -r
rand-mixed: -w --rand --randamount 524288 --rwmixpct 50

fio common arguments:
--name=contract --directory=/tmp/dtt-perf-contract-example
--filename_format=fio-file.$jobnum.$filenum --ioengine=libaio --thread=1
--numjobs=2 --nrfiles=2 --filesize=131072 --size=262144 --bs=4096
--direct=1 --iodepth=1 --fallocate=none --invalidate=0 --group_reporting=1
--rwmixread=50 --output-format=json --output=RESULT
seq-write: --rw=write
seq-read: --rw=read
rand-mixed: --rw=randrw

Read and mixed runs use files fully written by the corresponding seq-write.
These tiny runs validate output contracts; they are not performance claims.
