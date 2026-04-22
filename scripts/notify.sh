#!/bin/bash
# DingoFS Storage Testsuite Tools - WeChat Notification Script
# Sends test results to WeChat webhook

# Global variables (set by entrypoint.sh via environment)
WECHAT_ENABLED="${WECHAT_ENABLED:-no}"
WEBHOOK_URL="${WEBHOOK_URL:-}"

# Log function for notifications
log_notify() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Send WeChat notification
# Usage: send_wechat_notification <tool> <scenario> <status> <duration> [details]
send_wechat_notification() {
    local tool="$1"
    local scenario="$2"
    local status="$3"
    local duration="$4"
    local details="${5:-}"

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

**Tool:** ${tool}
**Scenario:** ${scenario}
**Duration:** ${duration}

| Tool | Scenario | Duration | Status |
|------|----------|----------|--------|
| ${tool} | ${scenario} | ${duration} | ${status} |"

    # Add details if provided
    if [[ -n "$details" ]]; then
        content="${content}

**Details:** ${details}"
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
