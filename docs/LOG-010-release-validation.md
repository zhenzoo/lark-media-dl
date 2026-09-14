---
doc_type: LOG
doc_id: LOG-010
title: 首次发布实际验收
status: active
purpose: Record observed results and the limits of the release checks.
owns:
  - dated validation evidence
does_not_own:
  - future platform guarantees or installation instructions
read_when:
  - assessing the tested scope of the first release
last_reviewed: 2026-09-14
---

# 首次发布实际验收

## 2026-09-14 Windows 与独立妙搭应用

- 从仓库创建独立 Python 3.13 虚拟环境并安装包，CLI 和 doctor 可用；注册到隔离 Agent home 后包装入口可调用，已有个人 Skill 保持原状。
- 19 项 Python 离线测试通过：目标帖/平台校验、图集、无正文错误、文件名冲突、配置优先级、网络失败不发布半成品、Worker 成功/失败、Key 重定向保护、安装冲突与卸载保护。
- 4 项妙搭合同测试及 TypeScript 检查通过；生产构建通过。将构建产物单独复制到不含开发依赖的目录，服务器持续运行。
- 在新建妙搭应用上完成正式发布，并回读线上业务表。修正云端 npm 镜像缺少 Rollup 包、SDK 的 @nestjs/config 运行依赖，以及 dev/online 数据库角色差异。
- 登录新网页提交一条公开 Threads 图文，Worker 主动领取，默认保存到真实用户 Downloads：2 张 JPEG 和 1 个 TXT。数据库回读 status=completed、progress=100、delivery_url=NULL，网页显示“已保存到电脑”。
- Worker 错误 Key 返回 403；未登录的网页 API 请求转去登录。服务端再次校验 Key，Worker 数据库服务身份只在该校验之后建立。
- Windows 启动脚本在隔离的 Startup 目录实际生成并通过 wscript 启动隐藏 Worker；状态文件中的 PID 与持续云端心跳可核验。这验证了启动命令与后台运行，未重启电脑，不能称为冷启动验收。
- 隐藏 Worker 持续运行时，再从网页提交 X 视频；无需前台下载命令，后台完成并回传“已保存到电脑”。
- X 公开视频、YouTube 480p 视频、Bilibili 480p 视频实际保存为 MP4，分别用 FFmpeg 解码前 2 秒成功。YouTube 元数据查询也通过。
- 小红书使用公开页面当次提供的完整分享参数，图文保存 1 张 JPEG 和正文 TXT，视频保存约 9.7MB MP4 和正文 TXT；未向公开包复制 Cookie。
- 可选 OSS：使用部署者凭据做真实小文件私有上传，V4 签名下载 HTTP 200、内容逐字节一致；不带签名访问 HTTP 403。仅验证对象上传/签名链路，没有拿小文件结果证明大视频或所有地域已通过。
- README 截图来自该独立应用的真实完成状态，不是界面模拟图。

## 验收边界

这是 Windows 隔离虚拟环境和独立云端应用验收，不等同于一台无历史配置的物理新电脑。目标平台的网络和 Key 通过显式用户配置供给，源码与公开仓库不包含这些值。

小红书适配保留 TikHub 与公开页面路径，本轮图文和视频各验证一条公开链接。Threads 其他内容类型的源模块已有文字、图集、视频、无声视频及多帧动图验证，公开包本轮的真实云端路径为图文。

仓库提供 Windows/macOS/Linux 安装 CI，三种登录配置格式已通过离线检查；CI 执行结果另行回执，登录服务与电脑冷启动仍需在部署者目标机器验收。平台接口、Cookie、付费权限、代理出口、不同媒体大小都会影响实际结果。

本版没有妙搭文件存储交付适配、Cloudflare 一键部署、多电脑任务定向或公开匿名下载站。程序失败会报告原因，不把未完成的结果声明为成功。
