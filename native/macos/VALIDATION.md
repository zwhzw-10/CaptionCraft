# CaptionCraft Mac preview 1 验证记录

验证日期：2026-10-19。环境：Apple Silicon、macOS 26.5.2、Google Chrome。

## 已验证

- 40 项 Python 测试通过，包括 7 项 Mac 适配测试。
- 验证本地安装、路径含空格时的运行、Native Messaging 消息与断开清理。
- Chrome 实际标签页音频捕获：英文 Whisper 与 Sherpa 流式识别均显示字幕。
- Whisper 英文识别与中文翻译显示为双语字幕。
- 修复原生 video 全屏时字幕不可见的问题，验证进入与退出全屏。
- 已通过 8 个 JavaScript 测试套件。

## 测试边界

本构建面向 Apple Silicon / macOS 14+；实际验收运行于 macOS 26.5.2，未覆盖所有受支持系统版本。未覆盖 Intel、Chrome Beta/Canary、Edge、Safari。安装流程通过命令行执行并在真实 Chrome 中验证；未完成全新机器下载后双击安装器 GUI 的完整验收。

安装器尚未使用 Developer ID 签名或公证。首次模型下载依赖网络；本次成功的本地语音样本测试不能保证所有网络环境下的下载成功率。

尚未验证真实 YouTube 视频下载的网络兼容性、长时间直播、多语言与噪声场景、独立字幕窗口的全部交互。流式引擎在短样本中仍可能漏词；显示的处理耗时不代表完整端到端延迟。

## 构建与依赖

构建方法见 [README](README.md)，精确依赖见 `requirements.lock`，运行时来源及校验值见 `runtime-sources.json`。发行包保留第三方许可证与依赖元数据。
