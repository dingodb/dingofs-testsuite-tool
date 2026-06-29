# dtt --setup-env 设计文档

## 概述

让 dtt 在运行测试前自动创建 DingoFS 文件系统并挂载，实现"一条命令完成环境准备 + 测试执行"。

## CLI 接口

新增两个参数，对所有工具（fio/vdbench/mdtest/pjdtest/ltp/int/mlperf）生效：

```
--setup-env <env名>    使用 env_setup 创建文件系统并挂载，env 查找优先级:
                       /custom/<env>.yaml → conf/env/<env>.yaml
--cleanup              测试结束后卸载并删除文件系统（仅配合 --setup-env 使用）
```

## env YAML 查找

`<custom_dir>` 来自 `dtt config set custom`：
```
1. <custom_dir>/<env_name>.yaml       ← 用户自定义
2. conf/env/<env_name>.yaml           ← dingofs-integration-test 内置 preset
```

## YAML 格式

与 `dingofs-integration-test/conf/env/*.yaml` 一致，支持 `base` 继承。mount_path 写宿主机路径：

```yaml
my_env:
  base: env_126_base
  clients:
    - fs_name: test-fs-1
      mount_path: /mnt/disk5/dingo_autotest/client/my_test
      client_conf:
        --cache_group: test_cache_group
```

## 执行流程

`dtt -t fio -s seq_read --setup-env env_126_dtt_smoke`：

```
1. dtt 在宿主机执行:
   python3 <integration_test>/tests/test_env_setup.py env_126_dtt_smoke

2. test_env_setup.py 内部:
   - 解析 yaml 配置
   - 创建文件系统（dingo fs create）
   - 配置客户端并挂载到 mount_path
   - 执行 dtt config set testdir <mount_path>   ← 自动更新配置

3. dtt 从 config 读取更新后的 testdir, 启动 Docker 容器, 执行测试

4. 如果 --cleanup: 卸载、删除文件系统
```

### 关键点

- `test_env_setup.py` 已有 `__main__` 入口，内部自动调用 `dtt config set testdir`，无需 dtt 侧额外处理 testdir 覆盖
- env_setup 在宿主机执行，测试在容器内执行（和 smoke_run 模式一致）

## 改动范围

### dingofs-testsuite-tool
- `run_testsuite()`：新增 `--setup-env` 和 `--cleanup` 参数解析
- `--setup-env` 生效时：先调用 `test_env_setup.py`，再走正常测试流程
- 指定 `--cleanup` 时：测试结束后调用 `env_cleanup` 清理

### entrypoint.sh
- 无需改动（setup 在宿主机侧完成）
