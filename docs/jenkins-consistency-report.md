# daily 一致性测试持续时间

`dtt daily` 在集成测试结束、生成报告前，通过 SSH 免密读取 Jenkins 父任务的构建记录，生成一份带统计时间的快照。不使用 Jenkins HTTP API，不需要 API Token。邮件、企业微信、Allure 页面使用相同数据；开启 `--ai-analysis` 后也不会重新查询或改变统计时间。

默认统计两个任务，在同一张表格中各占一行，分别计算连续时长：

[dingofs-stability-parent](http://172.30.14.128:8080/job/dingofs-stablity-test-40-41-42/job/dingofs-stability-parent/)

[dingofs-stability-3clients-mdsv2/deploy-metaserver](http://172.30.14.128:8080/view/dingofs-stability-test/job/dingofs-stability-3clients-mdsv2/job/deploy-metaserver/)

任务列显示完整项目名；“本段起点”和“最近中断”分别位于“统计时间”之后。每个任务独立采集，某个任务读取失败不会阻止其他任务显示，也不会改变 daily 测试结果。最近构建已经失败的任务显示失败，连续时长重置为 0，不累计中断之前的成功构建。

## 统计口径

- 只看父任务，不检查子任务、控制台日志或测试内容。
- 连续正常运行时长 = 连续 `SUCCESS` 父任务的实际 `duration` 之和 + 当前运行构建已经过的时间。
- 遇到 `FAILURE`、`ABORTED`、`UNSTABLE`、`NOT_BUILT` 即结束向前累计。下一次启动重新计时。
- 排队和两次构建之间的空闲时间不计入；父任务未运行时冻结数值，显示“当前无运行构建”。不读取全局队列，不区分等待下一轮和已经停止。
- 使用实际耗时，不用轮数乘以固定的两小时。父任务耗时包括其自身的准备、等待、收尾等阶段。
- 尚未找到失败边界且历史已被清理或达到查询上限时，显示“至少”，不假装是精确的完整历史。
- 构建号缺失、构建时间重叠或采集期间当前构建改变时，显示获取失败，避免拼接出错误的连续记录。
- 运行中只代表父任务尚未报告失败，不代表已经验证本轮成功。网页和邮件是快照，不是实时计时器。

默认连接 `jenkins@172.30.14.128`，只读取以下目录中各构建的 `build.xml`：

```text
/mnt/disk1/jenkins/jobs/dingofs-stablity-test-40-41-42/jobs/dingofs-stability-parent/builds
/mnt/disk1/jenkins/jobs/dingofs-stability-3clients-mdsv2/jobs/deploy-metaserver/builds
```

使用实际开始时间 `startTime`（缺失时回退 `timestamp`）、`duration`、`result` 和完成状态；运行中的耗时以 Jenkins 主机的时钟计算。最多读取 2000 个父构建，遇到最近的非成功边界即停止，SSH 采集总超时为 25 秒。采集前后检查 `jenkins` systemd 服务仍在运行。只读脚本通过 SSH 标准输入执行，不在远端安装脚本，不读取子任务、控制台日志或 Jenkins 凭据，不触发或取消构建。

## SSH 配置

126 宿主机的 `jenkins` 用户已经配置并验证了专用免密连接：

- 私钥：`$HOME/.ssh/dtt_jenkins_consistency`，权限 `600`。
- 公钥：`$HOME/.ssh/dtt_jenkins_consistency.pub`，已加入 128 上 `jenkins` 用户的授权文件。
- 受信主机公钥：`$HOME/.ssh/dtt_jenkins_known_hosts`，包含已核验的 128 主机公钥。

在其他机器运行时，需要为该机器的运行用户另行配置专用 SSH 密钥、授权公钥和受信主机文件；不要复制私钥进仓库或镜像，也不要关闭主机公钥校验。目标账号需要能够读取上述父任务记录、查询 systemd 服务状态，远端需要 `python3`。该采集程序只做读取，但普通 SSH 账号本身并非强制只读账号。

可单独验证免密连接（不会要求输入密码）：

```bash
ssh -F /dev/null \
  -i "$HOME/.ssh/dtt_jenkins_consistency" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$HOME/.ssh/dtt_jenkins_known_hosts" \
  jenkins@172.30.14.128 'id -un'
```

默认无需 JSON 配置。如密钥文件放在其他位置，设置宿主机环境变量：

```bash
export DTT_JENKINS_SSH_KEY=/安全目录/专用私钥
export DTT_JENKINS_KNOWN_HOSTS=/安全目录/受信主机公钥文件
```

`dtt daily` 只读挂载这两个文件到容器 `/tmp/dtt-jenkins-ssh-key` 和 `/tmp/dtt-jenkins-known-hosts`。环境变量及命令行只包含路径，不包含密钥内容；不把私钥复制进镜像、AI 输入或公开报告。容器用户必须有权限读取私钥：有测试挂载目录且不是 rootless 模式时，daily 使用该目录属主的 UID/GID。若与密钥属主不同，需调整运行身份或由该运行用户配置自己的专用免密密钥，不要把私钥改为所有人可读。

仅当连接信息变化时，才需要可选配置文件 `$HOME/.dingofs_testsuite/jenkins_consistency.json`。以下为兼容的单任务配置示例（显式指定顶层 `job_url` 或 `builds_dir` 时只采集该任务）：

```json
{
  "ssh_host": "172.30.14.128",
  "ssh_user": "jenkins",
  "ssh_port": 22,
  "jenkins_service": "jenkins",
  "builds_dir": "/mnt/disk1/jenkins/jobs/dingofs-stablity-test-40-41-42/jobs/dingofs-stability-parent/builds",
  "job_url": "http://172.30.14.128:8080/job/dingofs-stablity-test-40-41-42/job/dingofs-stability-parent/"
}
```

自定义多个任务时，把各自的 `job_url`、`builds_dir` 放入 `jobs` 数组；顶层 `ssh_host`、`ssh_user` 等作为共用连接配置，任务内可覆盖这些连接字段。不指定任务字段时默认采集上述两个任务。每个任务都有独立的统计时间和 25 秒超时。

`job_url` 仅用于报告中的浏览器链接，不用于认证或获取数据。配置文件不包含密码或 Token。daily 的默认配置目录可用 `DINGOFS_TESTSUITE_CONFIG_DIR` 修改，也可用 `DTT_JENKINS_CONFIG` 指定配置文件；存在时只读挂载到容器 `/tmp/dtt-jenkins-consistency.json`。显式指定了不存在的文件会显示获取失败，不会偷偷回退默认连接。

## 不跑存储测试，单独核对统计

在源码仓库根目录执行：

```bash
python3 dingofs-integration-test/src/jenkins_consistency.py
```

需要 JSON 时追加 `--format json`。单独执行脚本使用默认连接；如需自定义 JSON，请追加 `--config /路径/jenkins_consistency.json` 或设置 `DTT_JENKINS_CONFIG`。该命令只读取父任务记录；能正常取得统计时退出 0，配置或查询失败时退出 1。

## 在 daily 中使用

本功能涉及宿主机 CLI 和容器内代码，需要更新两部分。取得最新代码后运行：

```bash
./build.sh --debug
```

当前构建脚本也会更新本机 `~/.local/bin/dtt` 对应的 CLI；构建前会拉取集成测试和 chaos-tool 仓库，请先妥善处理本地未提交改动。构建时不需要提供私钥，镜像中仅安装 SSH 客户端及采集程序。

正常运行 daily，不需要额外的统计开关，例如：

```bash
dtt daily \
  --include client,cache_node \
  --email daigy@zetyun.com \
  --wechat \
  --daily \
  --report-path /mnt/disk5/daigy/tmp/output \
  --report-port 8889
```

## 报告位置与异常处理

- 邮件、企业微信：增加独立的一致性测试区域，不改变原来的测试通过/失败结论。
- Allure Overview 的 Environment：增加 `Jenkins.Consistency.*` 字段；内置兼容网页也显示这些字段。
- 报告根目录的 `index.html`：增加“一致性测试持续时间”链接。
- `jenkins-consistency.html` / `jenkins-consistency.json`：本次统计的网页版和原始数值，报告根目录存最新快照，每次生成的 Allure 历史报告目录也保留当次快照。
- AI 延迟通知：从当前运行的 `run_manifest.json` 读取同一份快照，不再查询 Jenkins。

密钥缺失或不可读、SSH 免密失败、主机公钥不匹配、连接超时、Jenkins 服务未运行或构建记录无法确认时，显示“获取失败/未能统计”，不当成绿色的零时长，不阻止原有报告发送，不修改 `dtt daily` 的测试退出码。`dtt smoke` 和 `dtt -t ...` 的行为不变。

首次人工核对的数据：北京时间 2026-09-14 10:23:15，父任务 #1469～#1497 连续成功 29 次，耗时合计 226189575 ms；#1498 已运行 7016304 ms；累计 233205879 ms，即 2 天 16 小时 46 分 45 秒。构建间隔合计 205235 ms，已扣除。这是历史核对样例，不是当前实时值。
