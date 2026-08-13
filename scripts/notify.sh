#!/bin/bash
# DingoFS Storage Testsuite Tools - WeChat and Email Notification Script
# Sends test results to WeChat webhook or Email

# Global variables (set by entrypoint.sh via environment)
WECHAT_ENABLED="${WECHAT:-no}"
WEBHOOK_URL="${WEBHOOK_URL:-}"
EMAIL_ENABLED="${EMAIL:-no}"
EMAIL_TO="${EMAIL_TO:-daigy@zetyun.com}"

# Email settings
EMAIL_HOST="${EMAILHOST:-smtp.partner.outlook.cn}"
EMAIL_PORT="${EMAILPORT:-587}"
EMAIL_USER="${EMAILUSER:-dingodb-ci@zetyun.com}"
EMAIL_PASS="${EMAILPASS:-_Dbfs@2025!}"
EMAIL_CC="${EMAILCC:-daigy@zetyun.com}"

# Log function for notifications
log_notify() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Send email notification
# Usage: send_email_notification <tool> <scenario> <status> <duration> [details] [test_date] [test_ip]
# Mount point is read from TEST_MOUNT env var (set by entrypoint.sh)
send_email_notification() {
    local tool="$1"
    local scenario="$2"
    local status="$3"
    local duration="$4"
    local details="${5:-}"
    local test_date="${6:-$(date '+%Y-%m-%d %H:%M:%S')}"
    local test_ip="${7:-$(hostname -I | awk '{print $1}')}"
    local mount="${TEST_MOUNT:-}"

    # Skip if email is not enabled
    if [[ "$EMAIL_ENABLED" != "yes" ]]; then
        log_notify "Email notification disabled (EMAIL=$EMAIL_ENABLED)"
        return 0
    fi

    # Skip if email address is not set
    if [[ -z "$EMAIL_TO" ]]; then
        log_notify "Email address not set (EMAIL_TO is empty)"
        return 1
    fi

    log_notify "Sending email notification..."
    log_notify "To: $EMAIL_TO"

    # Build email content
    local subject="[DingoFS] $tool 测试报告 - ${status}"
    local html_content="<!DOCTYPE html>
<html>
<body>
<h2>DingoFS 自动化测试报告</h2>
<p><b>测试日期：</b>${test_date}</p>
<p><b>测试节点IP：</b>${test_ip}</p>"
    if [[ -n "$mount" ]]; then
        html_content="${html_content}
<p><b>挂载点：</b>${mount}</p>"
    fi
    html_content="${html_content}
<table border='1' cellpadding='5' cellspacing='0'>
<tr><td><b>工具</b></td><td>$tool</td></tr>
<tr><td><b>场景</b></td><td>$scenario</td></tr>
<tr><td><b>状态</b></td><td>$status</td></tr>
<tr><td><b>耗时</b></td><td>$duration</td></tr>
</table>
<br>"

    if [[ "$tool" == "smoke" ]]; then
        # Smoke details format: "pjdtest[PASS] pass:587 fail:0 skip:1 total:588; mdtest[PASS]; ltp[PASS] pass:328 fail:0 skip:2 total:330"
        # Build a multi-tool HTML table from the smoke-specific format
        html_content="${html_content}
<h3>冒烟测试结果详情</h3>
<table border='1' cellpadding='5' cellspacing='0'>
<tr><th>工具</th><th>状态</th><th>通过 (Pass)</th><th>失败 (Fail)</th><th>跳过 (Skip)</th><th>总计 (Total)</th></tr>"

        # Parse each tool's section separated by newline
        local tools_sections=()
        while IFS= read -r line; do
            line=$(echo "$line" | xargs)
            [[ -n "$line" ]] && tools_sections+=("$line")
        done <<< "$details"
        for section in "${tools_sections[@]}"; do
            # Trim leading/trailing whitespace
            section=$(echo "$section" | xargs)
            [[ -z "$section" ]] && continue

            # Extract tool name: "pjdtest[PASS]" → tool=pjdtest, tool_status=PASS
            local tool_name="${section%%\[*}"
            local tool_status="${section#*\[}"
            tool_status="${tool_status%%\]*}"

            # Extract pass/fail/skip/total if present
            local t_pass="-"
            local t_fail="-"
            local t_skip="-"
            local t_total="-"
            if [[ "$section" =~ pass:[0-9]+ ]]; then
                t_pass=$(echo "$section" | sed -n 's/.*pass:\([0-9]\+\).*/\1/p')
                t_fail=$(echo "$section" | sed -n 's/.*fail:\([0-9]\+\).*/\1/p')
                t_skip=$(echo "$section" | sed -n 's/.*skip:\([0-9]\+\).*/\1/p')
                t_total=$(echo "$section" | sed -n 's/.*total:\([0-9]\+\).*/\1/p')
            fi

            # Color status
            local status_color="green"
            [[ "$tool_status" == "FAIL" ]] && status_color="red"
            [[ "$tool_status" == "TIMEOUT" ]] && status_color="orange"

            html_content="${html_content}
<tr><td>${tool_name}</td><td style='color:${status_color}'><b>${tool_status}</b></td><td>${t_pass}</td><td>${t_fail}</td><td>${t_skip}</td><td>${t_total}</td></tr>"
        done

        html_content="${html_content}
</table>"
    elif [[ "$details" =~ \|bw: ]]; then
        # fio performance metrics — format: "fio_read|d:0|bs:1MB|j:1|bw:1500MiB/s"
        html_content="${html_content}
    <h3>性能指标</h3>
    <table border='1' cellpadding='5' cellspacing='0'>
    <tr><th>场景</th><th>Direct</th><th>块大小</th><th>并发</th><th>带宽</th></tr>"
        while IFS= read -r mline; do
            [[ -z "$mline" ]] && continue
            local sname="${mline%%|*}"; local rest="${mline#*|}"
            local dv="${rest#*d:}"; dv="${dv%%|*}"
            local bv="${rest#*bs:}"; bv="${bv%%|*}"
            local jv="${rest#*j:}"; jv="${jv%%|*}"
            local bw="${rest#*bw:}"; bw="${bw%%|*}"
            html_content="${html_content}
    <tr><td>${sname}</td><td>${dv}</td><td>${bv}</td><td>${jv}</td><td>${bw}</td></tr>"
        done <<< "$(echo -e "$details")"
        html_content="${html_content}
    </table>"
    elif [[ "$details" =~ \|create: ]]; then
        # mdtest performance metrics — multi-scenario format:
        # "name|cmd:<cmd>|create:<v>|stat:<v>|read:<v>|remove:<v>|tcreate:<v>|tremove:<v>"
        html_content="${html_content}
    <h3>性能指标 (Mean ops/s)</h3>
    <table border='1' cellpadding='5' cellspacing='0'>
    <tr><th>场景</th><th>命令</th><th>File creation</th><th>File stat</th><th>File read</th><th>File removal</th><th>Tree creation</th><th>Tree removal</th></tr>"
        while IFS= read -r mline; do
            [[ -z "$mline" ]] && continue
            local sc_name="${mline%%|*}"
            local rest="${mline#*|}"
            local cmd_v="${rest#*cmd:}"; cmd_v="${cmd_v%%|*}"
            local cv="${rest#*create:}"; cv="${cv%%|*}"
            local sv="${rest#*stat:}"; sv="${sv%%|*}"
            local rv="${rest#*read:}"; rv="${rv%%|*}"
            local rmv="${rest#*remove:}"; rmv="${rmv%%|*}"
            local tcv="${rest#*tcreate:}"; tcv="${tcv%%|*}"
            local trv="${rest#*tremove:}"; trv="${trv%%|*}"
            html_content="${html_content}
    <tr><td>${sc_name}</td><td><small>${cmd_v:0:80}</small></td><td>${cv:-0}</td><td>${sv:-0}</td><td>${rv:-0}</td><td>${rmv:-0}</td><td>${tcv:-0}</td><td>${trv:-0}</td></tr>"
        done <<< "$(echo -e "$details")"
        html_content="${html_content}
    </table>"
    elif [[ "$details" =~ \|tp: ]]; then
        # elbencho performance metrics — format: "read|threads:32|tp:3168|avg:35.8|max:167"
        html_content="${html_content}
    <h3>性能指标</h3>
    <table border='1' cellpadding='5' cellspacing='0'>
    <tr><th>操作</th><th>并发数</th><th>吞吐量 (MiB/s)</th><th>平均延迟 (ms)</th><th>最大延迟 (ms)</th></tr>"
        while IFS= read -r mline; do
            [[ -z "$mline" ]] && continue
            local op="${mline%%|*}"
            local rest="${mline#*|}"
            local tv="${rest#*threads:}"; tv="${tv%%|*}"
            local tp="${rest#*tp:}"; tp="${tp%%|*}"
            local av="${rest#*avg:}"; av="${av%%|*}"
            local mx="${rest#*max:}"; mx="${mx%%|*}"
            html_content="${html_content}
    <tr><td>${op}</td><td>${tv}</td><td>${tp}</td><td>${av}</td><td>${mx}</td></tr>"
        done <<< "$(echo -e "$details")"
        html_content="${html_content}
    </table>"
    elif [[ -n "$details" ]]; then
        local passed_val=""
        local failed_val=""
        local pass_rate=""
        local failed_tests_list=""

        # Extract total (handle optional space after colon: "Total: 94" or "Total:94")
        if [[ "$details" =~ Total:[[:space:]]*[0-9]+ ]]; then
            total_val=$(echo "$details" | sed -n 's/.*Total:[[:space:]]*\([0-9]\+\).*/\1/p')
        fi

        # Extract passed (handle optional space after colon)
        if [[ "$details" =~ Passed:[[:space:]]*[0-9]+ ]]; then
            passed_val=$(echo "$details" | sed -n 's/.*Passed:[[:space:]]*\([0-9]\+\).*/\1/p')
        fi

        # Extract failed (handle optional space after colon; first occurrence before ". Failed:")
        if [[ "$details" =~ Failed:[[:space:]]*[0-9]+ ]]; then
            failed_val=$(echo "$details" | sed -n 's/.*Failed:[[:space:]]*\([0-9]\+\).*/\1/p')
        fi

        # Calculate pass rate
        if [[ -n "$total_val" ]] && [[ "$total_val" -gt 0 ]]; then
            pass_rate=$(awk "BEGIN {printf \"%.1f\", ($passed_val/$total_val)*100}")
            pass_rate="${pass_rate}%"
        fi

        # Extract failed test names (after ". Failed: ")
        if [[ "$details" =~ \.Failed:\  ]]; then
            failed_tests_list=$(echo "$details" | sed -n 's/.*\.Failed: \(.*\)/\1/p')
            # Replace comma separators with <br> for better readability in HTML
            failed_tests_list=$(echo "$failed_tests_list" | sed 's/, */<br>/g')
        fi

        # Build proper HTML table for test results
        html_content="${html_content}
<h3>测试结果详情</h3>
<table border='1' cellpadding='5' cellspacing='0'>
<tr><td><b>用例总数 (Total)</b></td><td>${total_val:-0}</td></tr>
<tr><td><b>通过用例数 (Passed)</b></td><td>${passed_val:-0}</td></tr>
<tr><td><b>失败用例数 (Failed)</b></td><td>${failed_val:-0}</td></tr>
<tr><td><b>通过率 (Pass Rate)</b></td><td>${pass_rate:-N/A}</td></tr>"

        # Add failed test details as last row if there are failures
        if [[ -n "$failed_tests_list" ]] && [[ "$failed_tests_list" != "0" ]]; then
            html_content="${html_content}
<tr><td><b>失败用例详情 (Failed Tests)</b></td><td><small>${failed_tests_list}</small></td></tr>"
        fi

        html_content="${html_content}
</table>"
    fi

    html_content="${html_content}
</body>
</html>"

    # Send email using curl with SMTP
    local payload=$(cat <<EOF
To: $EMAIL_TO
From: $EMAIL_USER
Cc: $EMAIL_CC
Subject: $subject
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

$html_content
EOF
)

    # Use swaks or curl to send email, fallback to simple mail command
    local sent=false

    if command -v swaks &> /dev/null; then
        swaks --to "$EMAIL_TO" \
              --from "$EMAIL_USER" \
              --cc "$EMAIL_CC" \
              --server "$EMAIL_HOST" \
              --port "$EMAIL_PORT" \
              --tls \
              --auth-user "$EMAIL_USER" \
              --auth-password "$EMAIL_PASS" \
              --header "Subject: $subject" \
              --html-body "$html_content" \
              &> /dev/null && sent=true
    elif command -v sendmail &> /dev/null; then
        echo "$payload" | sendmail -t &> /dev/null && sent=true
    else
        # Try using python3 to send email
        python3 << PYEOF
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

try:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '$subject'
    msg['From'] = '$EMAIL_USER'
    msg['To'] = '$EMAIL_TO'
    if '$EMAIL_CC':
        msg['Cc'] = '$EMAIL_CC'

    html_part = MIMEText('''$html_content''', 'html')
    msg.attach(html_part)

    server = smtplib.SMTP('$EMAIL_HOST', $EMAIL_PORT)
    server.starttls()
    server.login('$EMAIL_USER', '$EMAIL_PASS')

    to_addrs = ['$EMAIL_TO']
    if '$EMAIL_CC':
        to_addrs.append('$EMAIL_CC')

    server.sendmail('$EMAIL_USER', to_addrs, msg.as_string())
    server.quit()
    print("Email sent successfully")
except Exception as e:
    print(f"Email error: {e}")
    exit(1)
PYEOF
        if [[ $? -eq 0 ]]; then
            sent=true
        fi
    fi

    if [[ "$sent" == "true" ]]; then
        log_notify "Email notification sent successfully to $EMAIL_TO"
        return 0
    else
        log_notify "Failed to send email notification"
        return 1
    fi
}

# Usage: send_wechat_notification <tool> <scenario> <status> <duration> [details] [test_date] [test_ip]
# Mount point is read from TEST_MOUNT env var (set by entrypoint.sh)
send_wechat_notification() {
    local tool="$1"
    local scenario="$2"
    local status="$3"
    local duration="$4"
    local details="${5:-}"
    local test_date="${6:-$(date '+%Y-%m-%d %H:%M:%S')}"
    local test_ip="${7:-$(hostname -I | awk '{print $1}')}"
    local mount="${TEST_MOUNT:-}"

    # Skip if WeChat is not enabled
    if [[ "$WECHAT_ENABLED" != "yes" ]]; then
        log_notify "WeChat notification disabled (WECHAT_ENABLED=$WECHAT_ENABLED)"
        return 0
    fi

    # Skip if webhook URL is not set
    if [[ -z "$WEBHOOK_URL" ]]; then
        log_notify "WeChat webhook URL not set (WEBHOOK_URL is empty)"
        return 1
    fi

    # Build emoji and text based on status
    local emoji="✅"
    local status_text="**✅ PASS**"
    if [[ "$status" == "FAIL" ]]; then
        emoji="❌"
        status_text="**❌ FAIL**"
    elif [[ "$status" == "SUCCESS" ]]; then
        emoji="✅"
        status_text="**✅ SUCCESS**"
    else
        emoji="⚠️"
        status_text="**⚠️ $status**"
    fi

    # Build markdown content
    local content="${emoji} ${status_text}

测试日期：${test_date}
测试节点IP：${test_ip}"
    if [[ -n "$mount" ]]; then
        content+="
挂载点：${mount}"
    fi
    content+="

| Tool | Scenario | Duration | Status |
|------|----------|----------|--------|
| ${tool} | ${scenario} | ${duration} | ${status} |"

    # Add details if provided
    if [[ -n "$details" ]]; then
        if [[ "$details" =~ \|bw: ]]; then
            content="${content}

**FIO 性能指标:**
| 场景 | Direct | 块大小 | 并发 | 带宽 |
|------|--------|--------|------|------|"
            while IFS= read -r mline; do
                [[ -z "$mline" ]] && continue
                local sname="${mline%%|*}"; local rest="${mline#*|}"
                local dv="${rest#*d:}"; dv="${dv%%|*}"
                local bv="${rest#*bs:}"; bv="${bv%%|*}"
                local jv="${rest#*j:}"; jv="${jv%%|*}"
                local bw="${rest#*bw:}"; bw="${bw%%|*}"
                content="${content}
| ${sname} | ${dv} | ${bv} | ${jv} | ${bw} |"
            done <<< "$(echo -e "$details")"
        elif [[ "$details" =~ \|create: ]]; then
            content="${content}

**性能指标 (Mean ops/s):**
| 场景 | 命令 | File creation | File stat | File read | File removal | Tree creation | Tree removal |
|------|------|---------------|-----------|-----------|--------------|---------------|--------------|"
            while IFS= read -r mline; do
                [[ -z "$mline" ]] && continue
                local sname="${mline%%|*}"
                local rest="${mline#*|}"
                local cmd_v="${rest#*cmd:}"; cmd_v="${cmd_v%%|*}"
                local cv="${rest#*create:}"; cv="${cv%%|*}"
                local sv="${rest#*stat:}"; sv="${sv%%|*}"
                local rv="${rest#*read:}"; rv="${rv%%|*}"
                local rmv="${rest#*remove:}"; rmv="${rmv%%|*}"
                local tcv="${rest#*tcreate:}"; tcv="${tcv%%|*}"
                local trv="${rest#*tremove:}"; trv="${trv%%|*}"
                content="${content}
| ${sname} | ${cmd_v:0:50} | ${cv:-0} | ${sv:-0} | ${rv:-0} | ${rmv:-0} | ${tcv:-0} | ${trv:-0} |"
            done <<< "$(echo -e "$details")"
        elif [[ "$details" =~ \|tp: ]]; then
            content="${content}

**Elbencho 性能指标:**
| 操作 | 并发数 | 吞吐量 (MiB/s) | 平均延迟 (ms) | 最大延迟 (ms) |
|------|--------|----------------|--------------|--------------|"
            while IFS= read -r mline; do
                [[ -z "$mline" ]] && continue
                local op="${mline%%|*}"
                local rest="${mline#*|}"
                local tv="${rest#*threads:}"; tv="${tv%%|*}"
                local tp="${rest#*tp:}"; tp="${tp%%|*}"
                local av="${rest#*avg:}"; av="${av%%|*}"
                local mx="${rest#*max:}"; mx="${mx%%|*}"
                content="${content}
| ${op} | ${tv} | ${tp} | ${av} | ${mx} |"
            done <<< "$(echo -e "$details")"
        else
            content="${content}

**Details:**
${details}"
        fi
    fi

    # Send to WeChat webhook
    local payload=$(cat <<EOF
{
    "msgtype": "markdown",
    "markdown": {
        "content": "${content}"
    }
}
EOF
)

    log_notify "Sending WeChat notification..."
    log_notify "Webhook URL: $WEBHOOK_URL"
    log_notify "Status: $status"

    local response
    response=$(curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$payload")

    # Check curl exit code
    if [[ $? -eq 0 ]]; then
        log_notify "WeChat notification sent successfully"
        # Check if response contains error code
        if echo "$response" | grep -q '"errcode":0'; then
            log_notify "Response: $response"
            return 0
        else
            log_notify "WeChat API returned error"
            log_notify "Response: $response"
            return 1
        fi
    else
        log_notify "Failed to send WeChat notification (curl failed)"
        log_notify "Response: $response"
        return 1
    fi
}
