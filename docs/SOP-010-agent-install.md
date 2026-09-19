---
doc_type: SOP
doc_id: SOP-010
title: 让本地 Agent 完成安装与验收
status: active
purpose: Guide an agent from machine inspection to a verified personal installation.
owns:
  - installation, credentials, network checks and optional GUI setup
does_not_own:
  - implementation architecture or release history
read_when:
  - installing, updating or diagnosing this project
last_reviewed: 2026-09-14
---

# 让本地 Agent 完成安装与验收

用户可以把仓库地址和下面这段话交给 Claude Code、Codex 或 Kimi：

> 请阅读 README 和 docs/SOP-010-agent-install.md。调查这台电脑的系统、Python、网络、已有下载 Skill 和登录状态，安装个人 media-dl Skill，默认保存当前用户的 Downloads。先让我提供一条要下载的链接，只配置那个平台实际需要的东西。完成后用真实文件验证。除非我要求网页入口或手机下载，否则不配置飞书、Worker 自启动或 OSS。不要覆盖已有 Skill，不要在对话里输出密钥。

## 1. 先调查，再选择安装路径

1. 确认 Windows / macOS / Linux、CPU 架构、可用空间、当前用户 Downloads 是否可写。默认是用户主目录下的 Downloads；重定向到 OneDrive 或其他磁盘时，核对真实目录后设置 `MEDIA_DL_OUTPUT_DIR`。
2. 找到用户实际使用的 Agent 配置目录及已有 `media-dl` Skill。Codex 默认共享目录是 `~/.agents/skills`，Claude Code 默认是 `~/.claude/skills`；非默认 profile 必须查宿主配置。Kimi 的目录按已安装版本核对，不猜。
3. 检查 Python 3.10+、Git。缺失时从 [Python](https://www.python.org/downloads/) 和 [Git](https://git-scm.com/downloads) 获取适合系统的安装方式；仅安装用户需要的组件，不改别的项目环境。Linux 若缺 venv，按发行版安装对应 python-venv 包。
4. 阅读 `pyproject.toml` 后运行下面的预览，再安装。安装只写仓库的 `.venv`，不依赖作者的私人目录。
5. 不要求用户先注册所有服务。Threads 才必须走 TikHub；公开 YouTube、B 站、X 视频和 LinkedIn 帖子先尝试无需账号的路径（LinkedIn 页面通常需要媒体代理）。

在仓库根目录：

```sh
python scripts/bootstrap.py
python scripts/bootstrap.py --apply
```

Windows 使用 `.venv/Scripts/python.exe`；macOS/Linux 使用 `.venv/bin/python`。下文的 `<PY>` 都要替换成这个**实际解释器路径**，不是照抄尖括号。也可激活虚拟环境后用 `python`。

安装后执行：

```sh
<PY> -m media_dl.doctor --json
<PY> -m media_dl --help
```

FFmpeg 用于合并音视频和提取 MP3。优先使用已安装的 FFmpeg，常见系统由 imageio-ffmpeg 依赖提供二进制；不支持的架构需按 [FFmpeg 官方下载入口](https://ffmpeg.org/download.html) 单独安装。YouTube 还需要 yt-dlp 支持的 JavaScript 运行环境，优先复用已安装的 Deno 或受支持的 Node.js。版本要求核对 [yt-dlp EJS 文档](https://github.com/yt-dlp/yt-dlp/wiki/EJS)，不能把“有 node 命令”等同于版本兼容。

## 2. 配置只保存在用户电脑

从根目录 `.env.example` 选择所需项，保存到 `~/.config/lark-media-dl/.env`，或仓库外的自选文件。Windows 也支持这个用户目录；设了 `XDG_CONFIG_HOME` 时使用其下 `lark-media-dl/.env`。

读取优先级从低到高：用户配置 → `--env-file` 指定文件（或 `MEDIA_DL_ENV_FILE`；都未指定时才读当前目录 `.env`）→ 进程环境变量。排错时尤其检查旧进程变量是否覆盖新文件。显式指定的配置文件不存在会报错。

只回报“已配置 / 缺失 / 验证通过”，不输出值。密钥不写进命令历史、Git、截图、网页前端、公开日志或 Agent 长期记忆。账号注册、付费和浏览器登录由用户在自己的账号里完成，Agent 给准确入口并检查机械结果。

### Threads / TikHub

去 [TikHub](https://tikhub.io/) 注册自己的账号，按 [官方文档](https://docs.tikhub.io/) 创建 API Key、查看余额并确认 Threads 接口权限。写入 `TIKHUB_API_KEY`。Key 存在不等于接口可用，用用户提供的一条公开 Threads 单帖做真实请求验收。

默认 `TIKHUB_BASE=https://api.tikhub.dev`；按实际网络也可设为 `https://api.tikhub.io`。只把 Key 交给用户选择的可信 TikHub 地址。解析 API 与媒体文件下载用独立连接，TikHub Key 不发给媒体 CDN。

不需要 Threads Cookie，也不使用 Meta 发帖 Token。401/403 检查 Key 与接口权限，402 检查余额，429 稍后重试；私密、删除或不可访问帖子不承诺下载。

### YouTube / Bilibili / X / 小红书

- YouTube：先试公开视频。涉及账号权限时，由用户登录自己的浏览器；仅在获得其同意后，用 yt-dlp 支持的 `--cookies-from-browser chrome` 等方式读取登录状态。Windows 浏览器加密或文件锁可能使读取失败，不能因此尝试绕过浏览器保护；改用官方支持的 Cookie 文件流程。
- Bilibili：先试公开内容。无登录时清晰度受平台限制；登录 Cookie 只能获得该账号已有的权限，不能承诺大会员或付费内容。
- X：当前走免费 FxTwitter 解析公开视频，不需要 X API Key；只实现视频及可提取的音轨，不承诺纯文字、图集或一帖多个视频全部保存。
- 小红书：TikHub 详情接口和公开页面解析两条路径；保留分享链接里的 `xsec_token` 等参数。必要时配置自己的 Netscape Cookie 文件。当前小红书适配器不支持直接读浏览器 Cookie。

Cookie 文件按平台分别配置：`MEDIA_DL_YOUTUBE_COOKIES`、`MEDIA_DL_BILIBILI_COOKIES`、`MEDIA_DL_XIAOHONGSHU_COOKIES`。也可单次传 `--cookies`。文件不要上传仓库，失效后让用户重新登录。音频模式要求实际音轨；无声视频或纯文字帖子会明确失败。

### 网络调查

先测试用户目标平台，不修改全机代理。执行 `<PY> -m media_dl.doctor --platform threads --network --json`，按目标换平台名。它检查连通性，不证明账号权限或媒体一定可下载。

若连接失败，分别检查 DNS、站点访问、已运行的代理和实际监听端口；不复制作者的端口。需要时设 `MEDIA_DL_PROXY=http://127.0.0.1:实际端口`，也支持带 socks 协议的代理（需要其对应客户端依赖）。本版本打包的 requests 默认 HTTP/HTTPS 代理；若选择 SOCKS，先安装 `requests[socks]`。单次 `--proxy ""` 可明确直连。

TikHub 解析 API 默认直连；媒体 CDN 下载使用媒体代理。Worker 到妙搭的连接单独直连。出现“能取详情但下载失败”时，分别测试 API 与媒体 CDN，不把它们当成一条网络链路。

## 3. 注册 Skill，完成一条下载

先预览，再安装到**确认过的 Agent home**：

```sh
python scripts/install_skill.py --agent codex
python scripts/install_skill.py --agent codex --apply
# Claude Code: --agent claude
# 非默认配置或 Kimi: --agent kimi --home 实际配置目录
```

脚本写入 Skill 和调用本仓虚拟环境的入口，并保存自己的安装清单。发现已有同名 Skill、其他安装来源或用户编辑时会停止，不覆盖。已有另一套 media-dl 的电脑，先对比功能，再由用户选择保留原版或在独立 profile 试用；不默默装两个同名入口。仓库移动后应重新注册以更新解释器路径。

打开新的 Agent 会话，让它下载用户提供的一条公开链接；或直接运行：

```sh
<PY> -m media_dl "https://www.threads.com/@用户名/post/帖子代码" --json
<PY> -m media_dl "公开单条视频链接" --audio --json
<PY> -m media_dl "公开单条链接" --meta-only --json
```

核对实际目录中的文件能打开、数量与帖子一致、图片不是视频封面替代、音频确实可播放。再次下载同一帖应生成新文件名而不覆盖原文件。元数据模式不保存媒体。到这里，**个人 Skill / 命令行安装已完成**；无需飞书账号、OSS 或任何常驻 AI 会话。使用 Agent 本身的模型费用由用户所选产品决定，下载程序不调用大模型。

## 4. 可选：创建自己的妙搭网页

只有用户要“手机贴链接，电脑自己下载”时做这一节。

本版 GUI 基于妙搭全栈运行环境，前端 React、后端 NestJS、数据库保存队列。部署者需要自己的飞书账号和可用的妙搭应用权限；网页接口要求登录。默认保持应用仅本人可见。不要开放成陌生人可提交任务的公共下载服务。

1. 从 [Lark CLI 官方仓库](https://github.com/larksuite/cli) 安装 CLI，读取其 `lark-apps` 和 `lark-shared` 指引，检查版本及 `auth status`。缺权限时引导用户完成登录和授权，随后重新检查。需要 Node.js 22+ 与 npm 10+；云构建的依赖以本仓 lockfile 为准。
2. `lark-cli apps +create --as user --name "我的媒体工作台" --app-type full_stack`。保存返回的 app_id。用 `+init` 初始化**新的独立目录**；或按官方指引用 `+git-credential-init` 和 Git clone。不能把本 GitHub 仓库直接设成妙搭分支。
3. 阅读初始化目录里存在的 `.agents/skills/plugin-guide/SKILL.md`。从本仓根目录运行 `python scripts/export_miaoda.py 实际妙搭源码目录`，检查后加 `--apply`。只复制应用源码与配置模板，不复制任何作者身份、.env、依赖目录或任务历史。
4. 在妙搭源码目录装依赖，运行 `npm run typecheck`、`npm test`、`npm run build`。需要本地调试时运行 `lark-cli apps +env-pull --app-id 实际ID --as user`，所得 `.env.local` 属于用户自己的私密配置。
5. 查询数据库环境。新应用一般有 dev/online；多环境应用对 dev 执行 `server/database/001_initial.sql`，发布时同步结构；单环境应用才对 online 初始化。先查看表结构，已有表时不盲目重建，不手改系统表。使用 `+db-execute --file ...` 前按 CLI 当前帮助检查参数。SQL 包含两张表、队列索引与访问策略。
6. 用 `+openapi-key-create` 创建本应用独立的 Worker Key，只授权 `GET /openapi/jobs/next`、`POST /openapi/jobs/worker/heartbeat`、`POST /openapi/jobs/update`。原始 Key 只返回一次：Agent 应捕获到本地私密文件或密码管理器，不回显。
7. 把同一 Key 写到本应用服务端 `MEDIA_WORKER_API_KEY`，开发/线上环境分别配置。用 `+env-set --value -` 的标准输入或安全文件传值；不要把真实值嵌入命令。线上变更按用户明确授权执行。
8. 只提交审核过的源码到妙搭 `sprint/default`，push 后调用 `+release-create`，再用 `+release-get` 检查到 `finished`。不能把 Git push 成功当成已上线。检查线上两张业务表确实存在，使用返回的真实 online_url。
9. 创建电脑 Worker 的私密配置：
   `MEDIA_WORKER_API_BASE=应用的完整 online_url`（保留 /app/app_xxx 路径）、
   `MEDIA_WORKER_API_KEY=自己的Key`、
   `MEDIA_WORKER_ID=这台电脑的独立名称`、
   `MEDIA_DELIVERY=local`。平台下载配置写在同一文件或用户配置中。
10. `<PY> -m media_dl.worker --env-file 实际配置文件 --check` 只检查配置格式；再运行 `--once` 确认云端心跳和取任务成功。登录网页贴一条公开 Threads 链接，再执行 Worker，核对电脑文件和网页“已保存到电脑”；本地模式的完成记录应没有 deliveryUrl。

云端构建若报 npm 镜像 404，查看具体依赖与锁定版本，再核对镜像可用性；本仓固定 Rollup 4.62.2 是针对首次部署时镜像缺包。不要无区别切换下载源或删掉整个 lockfile。云平台内部故障与应用代码错误按实际发布日志分别处理。

同一个应用的多台 Worker **竞争领取任务**，不是每台都保存一份。若用户希望固定落到某台电脑，每台使用独立应用/队列；当前没有网页选目标电脑的功能。

## 5. 可选：登录后自动运行 Worker

先在前台验证真实下载，再安装自启动：

```sh
python scripts/startup.py --env-file 实际配置文件
python scripts/startup.py --env-file 实际配置文件 --apply
python scripts/status.py
```

Windows 写入当前用户 Startup 的隐藏启动脚本；macOS 使用当前用户 LaunchAgent；Linux 使用 systemd user service。它们是**登录自启动**，不是保证机器通电就能下载。首次安装脚本会启动后台；验证状态文件里的成功心跳及云端在线状态，不能只检查启动文件存在。

电脑须开机、已登录、联网、保持唤醒。锁屏、关显示器可以，睡眠或关机不能工作。关闭 Agent 会话、飞书桌面客户端不影响 Worker。电脑离线时任务排队；任务领取后超过 15 分钟不更新，会在下一次领取检查时重新排队。恢复可能重试整个任务；重复文件不会覆盖旧文件。

日志位于用户配置目录 `lark-media-dl/worker.log`，自动轮转。修改配置后重启对应 Worker；新进程才读取新配置。不要按“所有 python 进程”批量停止程序。

卸载自启动：`python scripts/startup.py --env-file 实际配置文件 --remove --apply`。Linux/macOS 同时停止对应服务；Windows 再核对 `scripts/status.py` 记录的 PID 的命令行确实属于此 Worker，停止这一个进程。取消 Skill：`python scripts/install_skill.py --agent 实际Agent --home 实际目录 --uninstall --apply`。它保留用户额外文件。需要移除 Python 包时，用本仓虚拟环境执行 `-m pip uninstall lark-media-dl`；Downloads 和私密配置由用户自己决定是否保留。

安装报告分别写：真实下载、登录后启动检查、重启电脑的冷启动检查。没重启电脑就不能声称冷启动通过。macOS/Linux 服务须在目标系统验收，不能用 Windows 上生成配置文件代替。

## 6. 可选：手机取回文件，启用 OSS

仅想用手机**提交**链接、让电脑下载，不需要本节。用户还想把结果下载到**手机存储**，才配置 OSS。它是阿里云对象存储，负责保存电脑已经下载好的结果；不会代替电脑从原平台抓视频。

1. 用户到 [阿里云 OSS](https://www.aliyun.com/product/oss) 开通自己的服务。Agent 引导创建私有 Bucket，选择实际地域，记录外网 HTTPS Endpoint 和地域 ID，说明存储和出站流量按账号实际计费。
2. 为 Worker 创建专用 RAM 身份，只授予自己 Bucket 下 `lark-media-dl/*` 的上传、下载及分片相关权限；不要直接使用主账号全权 Key。按 [官方断点续传说明](https://www.alibabacloud.com/help/en/oss/developer-reference/resumable-upload-1) 核对 `PutObject`、`ListParts` 等操作，私有 ACL 上传需要对应权限。用真实上传错误核实策略，不给全资源管理员权限。
3. 用户保管 `OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`；配置 `OSS_BUCKET`、`OSS_ENDPOINT`、`OSS_REGION`，以及 `MEDIA_DELIVERY=oss`。V4 签名必须带正确地域。
   为当前设备自动下载配置 Bucket CORS：来源填写用户实际工作台的 origin（协议和域名，不含应用路径），允许 GET/HEAD；不要把 Bucket 改成公共读。Agent 用浏览器确认签名文件可读取，不能只用 Python 下载成功代替 CORS 验证。网页会读取文件 Blob 后交给浏览器保存，保持标签页打开；失败时使用原有手动下载入口。
4. `python scripts/bootstrap.py --oss --apply` 安装可选依赖。配置 `OSS_URL_DAYS=1`（允许 1–7 天）。签名 URL 过期只让链接失效，**不会删除对象**；另为 `lark-media-dl/` 前缀配置用户认可的 Bucket 生命周期，例如 7 天删除。
5. 先用小文件验证：无签名访问被拒绝，签名链接能下载，内容一致；再走一条网页任务，确认手机按钮出现。多个结果临时打 ZIP 上传，电脑 Downloads 中仍是平铺的原文件。
6. 日常改回 `MEDIA_DELIVERY=local` 并重启 Worker，就恢复仅电脑保存；已有 OSS 对象仍遵循 Bucket 生命周期，不会被该开关删除。

本版支持 `local` 与 `oss` 两种交付。妙搭应用文件存储也提供上传及签名链接，当前 CLI 单文件上限 100MB（[官方说明](https://github.com/larksuite/cli/blob/main/skills/lark-apps/references/lark-apps-file.md)）；**本仓尚未接入该交付适配器**，不能告诉用户设个值就能代替 OSS。网页、队列、电脑下载本身可以只用妙搭加本机。

## 7. 有自己的域名或 Cloudflare，怎么迁移

Python 下载器和 Skill 完全不需要飞书。当前 `apps/miaoda` 使用妙搭 SDK 的登录、数据库与请求封装，不能直接扔到任意静态 Pages 就当作部署完成。

自托管需要把前端部署到用户域名，同时提供 HTTPS 后端、登录验证和持久化任务数据库，按 `apps/miaoda/shared/api.interface.ts` 与 `docs/openapi.json` 实现队列、领取、租约及心跳接口，替换妙搭 SDK。Cloudflare Pages 可以放前端；动态接口和队列仍需 Workers/其他后端及数据库。这个部署适配当前没有随仓库提供一键脚本。

妙搭只是现成的托管实现。免费额度、账号可用范围和服务政策以用户当前账号为准，不承诺永久免费或任意外部用户免登录。
