#!/bin/bash
# FIO纯顺序读批量测试脚本 - 预生成32个8G文件+所有场景复用+3遍结果合并
# 核心：仅预生成1次32个8G文件，后续所有读测试复用，direct=0前自动清缓存
# 结果文件：fio_logs/fio_result_d{0/1}_bs{xxx}_j{xxx}.log（同一场景3遍结果追加到同一文件）
# 测试文件：fio_test_file_1 ~ fio_test_file_32（8G/个，脚本开头一次性生成）
# 依赖：fio、sudo权限、足够磁盘空间（32*8G=256G，需确保磁盘剩余≥300G）

# ===================== 配置参数区（可根据需求修改）=====================
DIRECT_LIST=(1 0)          # direct=1(直接IO)、direct=0(缓存IO)
BS_LIST=("128KB" "1MB" "4MB")  # 块大小组合
NUMJOBS_LIST=(1 8 16 32)   # 并发数组合（最大32，匹配预生成文件数）
TEST_TIMES=3               # 每个场景执行次数
FILE_SIZE="8GB"            # 单个测试文件大小
FILE_NUM=32                # 预生成测试文件数量（≥最大numjobs，固定32）
IOENGINE="libaio"          # IO引擎
IODEPTH=1                  # IO队列深度
RW="read"                  # 测试模式：纯顺序读
GROUP_REPORT="--group_reporting"
TEST_FILE_PREFIX="fio_test_file"  # 测试文件前缀
RESULT_FILE_PREFIX="fio_result"   # 结果文件前缀
LOG_DIR="/home/dingofs/scripts/dgy/fio/fio_seq_read_logs"       # 日志文件存储目录（当前目录下的fio_logs）
# ======================================================================

# 检查磁盘空间（粗略检查，避免空间不足）
check_disk_space() {
    local required_space=$(( FILE_NUM * 8 ))  # 32*8=256G
    local free_space=$(df -P . | awk 'NR==2{print $4/1024/1024}')  # 当前目录剩余G
    if [ $(echo "$free_space < $required_space" | bc) -eq 1 ]; then
        echo -e "\033[31m【致命错误】当前目录剩余空间：$free_space G，至少需要 $required_space G！\033[0m"
        exit 1
    fi
}

# 检查fio是否安装
check_fio() {
    if ! command -v fio &> /dev/null; then
        echo -e "\033[31m【错误】未安装fio，请先安装：\033[0m"
        echo "CentOS/RHEL: yum install -y fio"
        echo "Ubuntu/Debian: apt install -y fio"
        exit 1
    fi
}

# 创建日志目录
create_log_dir() {
    if [ ! -d "${LOG_DIR}" ]; then
        echo -e "\033[33m【创建日志目录】不存在 ${LOG_DIR} 目录，开始创建...\033[0m"
        mkdir -p "${LOG_DIR}"
        if [ $? -eq 0 ]; then
            echo -e "\033[32m【创建成功】日志目录 ${LOG_DIR} 已创建完成！\033[0m"
        else
            echo -e "\033[31m【创建失败】无法创建日志目录 ${LOG_DIR}，请检查权限！\033[0m"
            exit 1
        fi
    else
        echo -e "\033[36m【目录已存在】日志目录 ${LOG_DIR} 已存在，直接使用...\033[0m"
    fi
    echo -e "=====================================\n"
}

# 主测试函数
run_fio_tests() {
    # 遍历所有测试组合
    for direct in "${DIRECT_LIST[@]}"; do
        for bs in "${BS_LIST[@]}"; do
            for numjobs in "${NUMJOBS_LIST[@]}"; do
                # 结果文件名：日志目录下的文件，同一场景3遍结果追加到同一文件
                local result_file="${LOG_DIR}/${RESULT_FILE_PREFIX}_d${direct}_bs${bs}_j${numjobs}.log"
                # 拼接本次测试使用的文件（按并发数取前numjobs个：1~numjobs）
                local use_files=""
                for ((i=1; i<=$numjobs; i++)); do
                    use_files+="${TEST_FILE_PREFIX}_$i:"
                done
                use_files=${use_files%:}  # 去掉最后一个冒号

                # 打印场景开始信息
                echo -e "\n====================================="
                echo -e "\033[32m【场景开始】direct=$direct | bs=$bs | numjobs=$numjobs（共跑$TEST_TIMES遍）\033[0m"
                echo -e "结果文件：\033[33m$result_file\033[0m（3遍结果追加保存）"
                echo -e "使用文件：$use_files"
                echo -e "=====================================\n"
                # 清空结果文件（避免重复执行时追加旧数据）
                > $result_file

                # 循环执行指定次数
                for ((test_num=1; test_num<=$TEST_TIMES; test_num++)); do
                    echo -e "\033[36m【开始第$test_num/$TEST_TIMES遍测试】$(date +%Y-%m-%d\ %H:%M:%S)\033[0m" | tee -a $result_file
                    
                    # direct=0时，执行前强制清理页缓存（需sudo）
                    if [ $direct -eq 0 ]; then
                        echo -e "\033[36m【清理缓存】执行：sudo echo 3 > /proc/sys/vm/drop_caches\033[0m" | tee -a $result_file
                        if ! sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>&1; then
                            echo -e "\033[31m【警告】缓存清理失败！请检查sudo权限，继续测试...\033[0m" | tee -a $result_file
                        fi
                        sleep 1  # 确保缓存清理完成
                    fi

                    # 拼接FIO读测试命令（--name统一为fiotest）
                    local fio_cmd="fio --ioengine=${IOENGINE} --iodepth=${IODEPTH} --direct=${direct} \
--rw=${RW} --bs=${bs} --size=${FILE_SIZE} --numjobs=${numjobs} \
 ${GROUP_REPORT} --name=fiotest"  # 统一name为fiotest

                    # 执行FIO命令，结果追加到日志文件+打印到控制台
                    echo -e "执行命令：$fio_cmd\n" | tee -a $result_file
                    $fio_cmd 2>&1 | tee -a $result_file

                    # 测试结果判断
                    if [ $? -eq 0 ]; then
                        echo -e "\033[32m【第$test_num遍完成】结果已追加到 $result_file\033[0m" | tee -a $result_file
                    else
                        echo -e "\033[31m【第$test_num遍失败】FIO执行出错！\033[0m" | tee -a $result_file
                    fi

                    # 单次测试间隔，避免磁盘高负载
                    echo -e "\033[36m【间隔休眠】2秒后开始下一遍测试...\033[0m\n" | tee -a $result_file
                    sleep 2
                done

                # 同一场景所有遍数完成
                echo -e "\033[32m【场景完成】direct=$direct, bs=$bs, numjobs=$numjobs 所有$TEST_TIMES遍测试结束！\033[0m"
                echo -e "=====================================\n"
                sleep 3  # 场景间休眠，缓解磁盘压力
            done
        done
    done
}

# 脚本主流程
main() {
    clear
    echo -e "====================================="
    echo -e "\033[32mFIO 纯顺序读批量测试（预生成文件版）\033[0m"
    echo -e "====================================="
    # 前置检查
    check_fio
    check_disk_space
    # 创建日志目录
    create_log_dir
    # 执行所有测试
    run_fio_tests
    # 测试完成汇总
    echo -e "\033[32m=====================================\033[0m"
    echo -e "\033[32m【全部测试结束】$(date +%Y-%m-%d\ %H:%M:%S)\033[0m"
    echo -e "\033[32m=====================================\033[0m"
    local scene_num=$(( ${#DIRECT_LIST[@]} * ${#BS_LIST[@]} * ${#NUMJOBS_LIST[@]} ))
    local total_test=$(( scene_num * TEST_TIMES ))
    echo "总测试场景数：$scene_num 个"
    echo "总测试次数：$total_test 次"
    echo "预生成测试文件：$FILE_NUM 个 $FILE_SIZE（共$((FILE_NUM*8))G）"
    echo "结果文件数量：$scene_num 个（每个场景1个，含3遍测试结果）"
    echo -e "结果文件存储目录：\033[33m${LOG_DIR}\033[0m"
    echo -e "结果文件格式：${LOG_DIR}/${RESULT_FILE_PREFIX}_d{0/1}_bs{xxx}_j{xxx}.log"
    echo -e "\033[32m=====================================\033[0m"
    exit 0
}

# 执行主流程
main