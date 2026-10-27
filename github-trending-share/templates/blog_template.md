# 《标题：XXX 技术指南 / 部署实战》

> 作者：@你的昵称
> 日期：YYYY-MM-DD
> 关键词：技术栈 / 部署平台 / 工具名

---

## 一、前言（开篇必写，30 秒留住读者）

### 1.1 写作背景
我为什么写这篇？踩到了什么坑、遇到了什么问题，最终怎么解决的？
把真实的痛点直接抛出来，让读者一眼判断"这是不是我"。

### 1.2 适用人群
- ✅ 新手小白：零基础也能跟着走
- ✅ 进阶开发者：关注性能调优与安全加固
- ✅ 部署玩家：多环境 / 多容器 / 多云迁移
- ✅ Agent / AI 开发者：关注 LLM 接入与工具链

### 1.3 阅读收获
读完这篇，你能：
1. 独立完成 XXX 的从零搭建
2. 解决 90% 会遇到的常见报错
3. 掌握开机自启、守护进程、安全组放行等运维基本功

### 1.4 环境前置
| 类别 | 推荐版本 | 备注 |
|---|---|---|
| 操作系统 | Ubuntu 22.04 LTS / 24.04 LTS | 本文以 Ubuntu 为例 |
| 运行时 | Node.js 22.22.3+ / 24.15+ | 官方推荐 Node 24 LTS |
| 包管理器 | npm / pnpm | pnpm 需 approve-builds |
| 服务器规格 | 2 核 4GB（最低 2GB + Swap） | 4 核 8GB 推荐 |
| 系统盘 | ≥ 40GB SSD | 预留日志 / 插件空间 |

---

## 二、技术原理 / 核心概念（通俗讲解，不堆公式）

### 2.1 核心技术简单介绍
一句话讲清"这是什么"。

> 示例：OpenClaw 是一个开源的本地优先 AI Agent 框架，核心定位是**AI 智能体的执行网关**——它本身不思考，需要接入大模型作为大脑，但能为大模型赋予文件读写、命令执行、浏览器自动化等系统级操作权限。

### 2.2 工作流程与运行逻辑
- 用户在聊天渠道（Web UI / Telegram / 飞书 / CLI）发起请求
- Gateway 网关接收消息、路由到对应 Agent
- Agent 调用 LLM 进行任务规划（Reasoning / Tool Use）
- 执行工具链（Exec / Browser / File / API / Skills）
- 结果回传到渠道，形成闭环

### 2.3 新手最容易误解的点
1. ❌ 以为是"聊天机器人" → ✅ 实际是"会执行任务的 Agent"
2. ❌ 直接把默认端口暴露到公网 → ✅ 应该绑定 loopback 走 SSH / Tailscale
3. ❌ 随便装第三方 Skill → ✅ 只从官方仓库安装，注意权限范围

### 2.4 整体架构流程图（文字版）

```
┌─────────────────────────────────────────────────────────────┐
│                     用户 / 前端渠道                          │
│   Web UI · CLI · Telegram · 飞书 · Discord · iMessage ...    │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket / HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Gateway 网关 (WS 18789)                  │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────────────┐ │
│  │ Session   │  │ Auth/Token│  │ Control UI Dashboard     │ │
│  └───────────┘  └───────────┘  └─────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ RPC
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Pi Agent Runtime (执行引擎)                │
│  LLM 调用 → 任务规划 → Tool 调用 → 结果汇总 → 流式输出       │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐   ┌────────────┐   ┌────────────┐
   │ 本地工具   │   │ 外部 API    │   │ 插件 / Skill│
   │Exec/File   │   │OpenAI/阿里  │   │ClawHub      │
   │Browser     │   │云百炼/...   │   │自定义开发   │
   └────────────┘   └────────────┘   └────────────┘
```

---

## 三、准备工作（前置依赖）

### 3.1 服务器 / 环境准备
- 阿里云轻量应用服务器（或 ECS），镜像选择 **Ubuntu 22.04 LTS / 24.04 LTS**
- 中国内地地域（除香港）：联网搜索功能受限，建议选 **美国弗吉尼亚 / 新加坡**
- SSH 密钥对，禁用 root 密码登录（基础安全）

### 3.2 需要开启的端口、权限、配置
| 端口 | 用途 | 安全组策略 |
|---|---|---|
| 22 | SSH 远程登录 | 仅允许固定 IP 或使用密钥 |
| 18789 | Gateway 网关 Control UI | **不建议直接暴露公网**，走 SSH 隧道 / Tailscale |
| (可选) 443 | HTTPS 反代 | 如需公网访问，走 Nginx + SSL |

### 3.3 需要的密钥 / API Key / 账号权限
- ✅ 大模型 API Key（Anthropic / OpenAI / 阿里云百炼 / OpenRouter 任选）
- ✅ 渠道 Bot Token（如 Telegram BotFather）
- ✅ 阿里云账号（如果用 Token Plan 订阅方案）
- ✅ (可选) Tailscale 账号，用于安全远程访问

### 3.4 依赖软件安装清单
- Node.js ≥ 22.22.3 / 24.15+
- Git（`apt install -y git`）
- pnpm（可选，从源码构建才需要）
- Docker（可选，容器化部署方案）

---

## 四、分步实操教程（博客核心主体）

> 以下每一步都给出可直接复制的命令 + 关键参数说明。

### 步骤 1：初始化服务器环境

```bash
# 系统更新
sudo apt update && sudo apt upgrade -y

# 安装 Node.js 24 LTS（官方推荐默认版本）
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs git build-essential

# 验证版本（Node 需 ≥ 22.22.3 / 24.15+）
node -v
npm -v

# 国内用户可选：配置 npm 淘宝镜像加速
sudo npm config set registry https://registry.npmmirror.com
```

### 步骤 2：安装 OpenClaw（三种方式任选）

**方式 A — 官方安装脚本（最推荐）：**
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

**方式 B — npm 全局安装：**
```bash
npm install -g openclaw@latest
```

**方式 C — 从源码构建：**
```bash
git clone https://github.com/openclaw/openclaw.git
cd openclaw
corepack enable && pnpm install && pnpm build && pnpm ui:build
pnpm link --global
```

### 步骤 3：运行 Onboarding 向导

```bash
openclaw onboard --install-daemon
```

向导会依次让你选择：
1. 模型提供商（Anthropic / OpenAI / 阿里云百炼 / DeepSeek / Ollama ...）
2. 输入 API Key
3. 是否安装 systemd 守护进程（**必须选 Yes**，否则 SSH 断开服务就挂了）
4. Gateway 绑定地址（**推荐 loopback**，不直接暴露公网）

### 步骤 4：修改关键配置参数（重点标注）

配置文件路径：`~/.openclaw/config.json` 或通过 `openclaw configure` 交互式修改。

```json
{
  "gateway": {
    "bind": "loopback",            // ⚠️ 关键！不要用 0.0.0.0
    "port": 18789,
    "auth": {
      "token": "请生成一个强随机字符串作为访问令牌"
    }
  },
  "providers": {
    "qwen": {
      "apiKey": "sk-xxxxxxxxxxxxxxxxxxxx",
      "model": "qwen-max"
    }
  }
}
```

### 步骤 5：启动服务

```bash
# 启动 Gateway
openclaw gateway start

# 查看运行状态
openclaw gateway status

# 健康检查
openclaw health
```

### 步骤 6：开机自启配置（systemd 用户服务）

`openclaw onboard --install-daemon` 已自动安装。手动检查：

```bash
# 查看服务状态
systemctl --user status openclaw-gateway.service

# 设置用户级开机自启（需先 enable-linger）
sudo loginctl enable-linger "$USER"
systemctl --user enable openclaw-gateway.service

# 可选：systemd 性能调优
systemctl --user edit openclaw-gateway.service
```

调优内容：
```ini
[Service]
Environment=OPENCLAW_NO_RESPAWN=1
Environment=NODE_COMPILE_CACHE=/var/tmp/openclaw-compile-cache
Restart=always
RestartSec=2
TimeoutStartSec=90
```

### 步骤 7：防火墙 / 安全组放行配置

**阿里云安全组**（控制台操作）：
- 出方向：全部允许
- 入方向：
  - 22 端口 → 允许你的固定办公 IP
  - ~~18789 端口~~ → **不放行！** 通过 SSH 隧道 / Tailscale 访问

**SSH 隧道访问（推荐）：**
```bash
# 在本地电脑执行
ssh -N -L 18789:127.0.0.1:18789 root@你的服务器IP
# 然后本地浏览器访问 http://localhost:18789
```

**Tailscale 方案（更优雅）：**
```bash
# 服务器上安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 本地浏览器通过 Tailscale IP 直接访问 18789
```

---

## 五、功能测试与验证

### 5.1 本地测试命令

```bash
# 版本与健康检查
openclaw --version
openclaw doctor
openclaw gateway status --deep
openclaw health

# 发送一条测试消息
openclaw message send --to "你的测试会话" --message "你好，帮我列出当前目录"

# CLI 直接交互
openclaw agent --message "Ping 一下百度看看网络通不通" --thinking low
```

### 5.2 服务状态检查清单

| 检查项 | 命令 | 期望结果 |
|---|---|---|
| Gateway 进程 | `openclaw gateway status` | `running` 或 `active` |
| 端口监听 | `ss -tlnp \| grep 18789` | 监听 `127.0.0.1:18789`（loopback） |
| systemd 服务 | `systemctl --user status openclaw-gateway` | `active (running)` |
| API Key 连通性 | `openclaw health` | 无 Provider 报错 |
| 安全审计 | `openclaw security audit --deep` | 无高危项 |

### 5.3 日志查看排错

```bash
# 实时查看 Gateway 日志
journalctl --user -u openclaw-gateway.service -f

# 最近 100 行
journalctl --user -u openclaw-gateway.service -n 100

# 按错误级别过滤
journalctl --user -u openclaw-gateway.service -p err -f
```

### 5.4 功能调用演示结果
> 截图展示：Control UI 界面、CLI 交互、Telegram 渠道对话、Exec 工具执行结果。
> （占位，实际写博客时贴图）

### 5.5 成功运行效果图说明
> 一句话说明每张图展示了什么，读者应该看到什么才算正常。

---

## 六、常见报错 & 踩坑汇总（博客高价值点）

### 坑 1：端口占用 `EADDRINUSE`
```bash
# 查看占用进程
ss -tlnp | grep 18789
# 杀掉旧进程
pkill -f openclaw
# 或换端口
openclaw gateway start --port 18790
```

### 坑 2：权限不足 `Permission denied`
- 运行目录权限不够：`chmod -R 755 ~/.openclaw`
- systemd 用户服务没 enable-linger：`sudo loginctl enable-linger "$USER"`
- `exec` 工具被 SELinux / AppArmor 拦截 → 在 Docker 或沙箱里跑

### 坑 3：依赖缺失报错
- Node 版本太低：必须 ≥ 22.22.3，不要用 18 / 20
- `pnpm approve-builds -g` 忘记执行（pnpm 用户）
- `build-essential` 没装导致原生模块编译失败

### 坑 4：连接失败 / 外网访问失败
- 安全组没放行 22 端口
- Gateway 绑了 `loopback` 但忘了建 SSH 隧道
- 中国大陆服务器访问境外大模型 API 需要代理（在 config 里配 `httpProxy`）
- 云厂商 Token Plan 端点地址配错，国内用 `https://dashscope.aliyuncs.com/compatible-mode/v1`

### 坑 5：启动成功但功能不生效
- API Key 额度耗尽或模型名称写错
- onboarding 只跑了一半，某些渠道没配对完成
- `openclaw configure` 改完没 `openclaw gateway restart`

### 坑 6：服务器关机后服务消失
90% 新手忽略 `systemctl --user enable` + `loginctl enable-linger`，SSH 断开或重启后服务不会自启。**务必执行这两条命令！**

### 坑 7：Gateway 端口 18789 被扫到（ClawHavoc 安全事件）
> 2026 年 1 月已有超 23 万实例因暴露 18789 被全网扫描。
> ✅ 立即检查：`openclaw security audit --deep`
> ✅ 修复：把 `gateway.bind` 改成 `loopback`，走 SSH / Tailscale 访问
> ✅ 补 Token：设置 `gateway.auth.token`，禁用匿名访问

### 坑 8：OOM（内存不足被 kill）
```bash
# 加 Swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 低内存 VPS 调优
export NODE_COMPILE_CACHE=/var/tmp/openclaw-compile-cache
export OPENCLAW_NO_RESPAWN=1
```

---

## 七、性能优化 / 进阶玩法

### 7.1 内存优化
- 关闭不必要的插件：`openclaw plugins disable <name>`
- 降低 LLM `thinking` 级别：用 `low` / `medium` 代替 `high`
- 低内存主机启用 Swap + `OPENCLAW_NO_RESPAWN=1`

### 7.2 守护进程完善
- systemd 自动重启（见步骤 6 配置）
- `openclaw update --channel stable` 定期升级
- `openclaw update --dry-run` 先预览再升级

### 7.3 日志轮转
systemd journal 默认就会轮转，也可以手动配置：
```ini
# /etc/systemd/journald.conf
SystemMaxUse=500M
SystemKeepFree=100M
MaxRetentionSec=14day
```

### 7.4 多任务并发优化
- 多 Agent 路由：不同渠道 / 群组 → 不同 Agent，互相隔离
- 启用队列模式：`openclaw gateway config set queue.concurrency 3`
- 工具缓存：浏览器会话持久化、HTTP 请求结果缓存

### 7.5 结合其他工具联动玩法
- **Nginx 反代 + Let's Encrypt**：把 Gateway 用域名暴露（务必加 token 认证）
- **Cloudflare Tunnel**：比公网暴露更安全的穿透方案
- **飞书 / 钉钉机器人**：把 Agent 接入企业内部 IM
- **Cron 定时任务**：用 Agent 每天自动抓取信息、生成日报
- **本地 Ollama**：跑开源模型完全离线，隐私安全

---

## 八、总结（收尾）

### 8.1 本次搭建核心要点回顾
1. ✅ **Node 版本 ≥ 22.22.3**，别再用老教程里的 Node 18
2. ✅ **Gateway 绑 loopback**，18789 端口走 SSH / Tailscale，不直接暴露
3. ✅ **systemd enable + linger**，保证服务器重启后服务自启
4. ✅ **security audit --deep**，部署完一定要跑一遍安全检查
5. ✅ **API Key 走官方 / Token Plan**，省成本也稳定

### 8.2 最佳实践建议
- 新建专用 Linux 用户跑 OpenClaw，不要用 root
- 定期备份 `~/.openclaw` 目录：`tar czf openclaw-backup-$(date +%F).tar.gz ~/.openclaw`
- 只从官方 ClawHub 安装 Skill，陌生第三方先审代码再装
- 开启 DM 配对 + 群组白名单，防止陌生人给你的 Agent 发指令

### 8.3 后续可拓展方向
- 接入自定义大模型（本地 Ollama / 私有部署）
- 开发自己的 Skill 插件，发布到 ClawHub
- 容器化部署（Docker Compose + 数据卷持久化）
- 多 Gateway 集群，统一 Dashboard 管理

---

## 九、文末福利（可选）

> 把下面这些打包到网盘 / OSS / GitHub Release，评论区留领取方式。

- 📦 **一键部署脚本**：`install-openclaw.sh`（含 Node 24 + OpenClaw + systemd 全套）
- 📦 **生产级配置模板**：`config.production.json`（已加固，loopback + token）
- 📦 **systemd 单元文件**：已调好 RestartSec / 超时
- 📦 **阿里云安全组策略参考图**
- 📦 **常用 Skill 精选清单**（10 个经过安全审计的实用技能）

---

> 🦞 **Happy Clawing！** 有问题评论区交流，别让你的"小龙虾"裸奔。
