---
name: 11-01-SUMMARY.md
description: Add --wechat and --email CLI flags and config support
type: summary
phase: 11
plan: 11-01
status: complete
completed: 2026-04-21
---

## Summary

Added notification configuration basics: --wechat and --email CLI flags, and config support for webhook_url and email.

## What Was Built

- **dingofs-testsuite-tool** modifications:
  - Added WEBHOOK_URL_FILE, EMAIL_FILE, DEFAULT_WEBHOOK_URL, DEFAULT_EMAIL variables
  - Updated load_config() to handle webhook_url and email keys
  - Updated save_config() to handle webhook_url and email keys
  - Updated show_help() with notification options and examples
  - Updated cmd_config to accept webhook_url and email config keys
  - Updated cmd_config show to display webhook_url and email values
  - Added --wechat and --email flag parsing in run_testsuite()
  - Added env var passing for WECHAT, WEBHOOK_URL, EMAIL, EMAIL_TO to docker container

- **entrypoint.sh** modifications:
  - Added WECHAT_ENABLED, WEBHOOK_URL, EMAIL_ENABLED, EMAIL_TO global variables
  - Added notification options to help text

## Tasks Completed

1. **Task 1**: Update dingofs-testsuite-tool with notification config variables ✓
2. **Task 2**: Update dingofs-testsuite-tool load_config and save_config functions ✓
3. **Task 3**: Update dingofs-testsuite-tool help text and examples ✓
4. **Task 4**: Update dingofs-testsuite-tool run_testsuite with --wechat/--email flags ✓
5. **Task 5**: Update entrypoint.sh with notification environment variables ✓

## Acceptance Criteria Status

- [x] `dtt config set webhook_url <url>` works
- [x] `dtt config set email <addr>` works
- [x] `dtt config show` displays webhook_url and email
- [x] `--wechat` flag passes WECHAT=yes and WEBHOOK_URL to container
- [x] `--email` flag passes EMAIL=yes and EMAIL_TO to container
- [x] Help shows --wechat and --email options
- [x] Examples show how to enable notifications
- [x] entrypoint.sh accepts WECHAT, WEBHOOK_URL, EMAIL, EMAIL_TO environment variables
- [x] Help text mentions notification options

## Files Modified

- dingofs-testsuite-tool (added notification config support)
- entrypoint.sh (added notification env var handling)

## Requirements Addressed

- NOTIFY-01: 添加 `--wechat` 命令行参数启用微信通知 ✓
- NOTIFY-02: 添加 `--email` 命令行参数启用邮件通知 ✓
- NOTIFY-03: 在 dtt config 中设置 webhook_url（微信） ✓
- NOTIFY-04: 在 dtt config 中设置 email 地址 ✓
- NOTIFY-05: webhook_url 默认值使用配置中的值 ✓
- NOTIFY-06: email 默认发送到 daigy@zetyun.com ✓

## Next Steps

Phase 12 will implement the actual WeChat webhook notification sending functionality.
