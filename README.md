# 字幕翻译生成 · CaptionCraft 0.7.0 测试版

## Mac 测试版

已增加 Apple Silicon（M 系列）macOS 14+ 安装器和原生助手适配。使用 Mac 安装包，解压后打开安装器；不要运行 Windows EXE。内置 Python，首次仍需在 Chrome 加载扩展。构建与数据目录见 [Mac 说明](native/macos/README.md)。下载 [Mac preview 1](https://github.com/zwhzw-10/CaptionCraft/releases/tag/v0.7.0-macos-preview.1)；安装步骤见 [使用说明](native/macos/USER-GUIDE.zh-CN.txt)，测试范围与限制见 [验证记录](native/macos/VALIDATION.md)。

Windows / Chrome 本地视频及直播字幕。新增实时双语、通用网页音频捕获、英文流式引擎、独立字幕窗口；保留 YouTube 普通视频的预先生成与时间同步功能。尚未上架 Chrome 商店。

## 安装和升级

普通用户仅需运行 **CaptionCraft-All-in-One-Setup-v0.7.0.exe**，点击“安装助手和插件”。完成后点击“复制路径并打开 Chrome”。在 `chrome://extensions` 开启开发者模式 → 加载未打包的扩展程序，在文件夹选择窗口地址栏粘贴路径、回车，再点“选择文件夹”。不要进入 icons / _locales 子文件夹；窗口看不到 manifest.json 属正常现象。

已装旧版的用户需要加载安装器准备的新 0.7.0 文件夹，不能只刷新旧 0.6 文件夹。可先在 Chrome 移除旧扩展，再加载新目录；移除扩展可能重置 Chrome 内保存的样式和语言设置。助手程序使用新版本目录，已有 Data 中的识别和翻译模型会保留。无需 Python、命令、Start.cmd 或手动合并旧补丁。

安装目录 `%LOCALAPPDATA%\CaptionCraft` 不要移动；下载的安装 EXE 可在安装后归档。Chrome 要求首次由用户确认加载扩展，本版不能静默安装。扩展稳定 ID 与 0.6.0 保持一致：`gnpbaionpkfpjgpcccjbnjbhlhlnjlcm`。

## 两种字幕模式

- **同步字幕**：YouTube 普通视频，优先已有字幕，否则先获取音频并分段识别，再按视频进度显示。未准备的片段会暂停，准备好后自行播放。当前直播检测仅能识别明显直播标记，不能保证判断所有播放器；正在直播请手动选择实时模式。
- **实时字幕**：YouTube 直播及普通 HTTP/HTTPS 网页，捕获用户点击启动的标签页声音。原文先出现，译文随后补充；只有译文模式在翻译准备期间显示等待提示。字幕始终可能晚于声音，不承诺零延迟或所有网站兼容。

选择音频语言为 **English**，引擎“自动选择”会使用 Sherpa 本地流式英语模型。自动识别语言及其他语言使用 Whisper 的滚动窗口方案。流式英语模型速度快，但词汇、口音、噪声准确率未做广泛验证；可手动选“多语言 Whisper”兼容引擎。强制英语流式时源语言必须选择英语。

输入每 0.5 秒更新，最多保留 6 秒 PCM。Sherpa 只消费重叠窗口中的新音频，保持语音上下文，在停顿处确认文字并重置句子状态。临时字幕会修正。Whisper 仍是滚动识别，不能称作完整原生流式模型。独立翻译线程保留一个运行任务和一个最新待处理任务，不阻塞原文识别，过期译文不会替换新句子。

浮层共用字号、背景、透明度、拖动设置，可拖到网页的视频区域之外。特殊 iframe / 原生全屏播放器无法嵌入浮层时，可打开“独立字幕窗口”；这是普通 Chrome 弹窗，不保证系统级置顶。SRT 导出仍用于已准备的视频字幕，实时字幕暂不保存完整历史。

## 语言、模型与资源

- 原文语言：英语、日语、法语、西班牙语、韩语、俄语。翻译目标另有中文。界面七种语言。
- 首次启动基础多语言 Base Whisper 需约 145 MB 模型下载。英语流式模式首次额外下载官方归档约 122 MiB，校验 SHA256 后只保留约 42 MiB 的 int8 模型数据。以后缓存完整即可离线识别。
- 翻译模型按方向下载，可能数百 MB；部分语言需经英语中转，耗时和误译风险增加。首次联网获取的是模型，不是把录音发到云端。
- Windows 10/11 x64，建议至少 8 GB 内存和数 GB 磁盘空间；无需独立显卡。首次准备、翻译及真实字幕延迟依网络、电脑、模型和讲话方式变化。
- 英语模型来源：[sherpa-onnx 官方说明](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html)。版本 `sherpa-onnx==1.13.8`；基础识别 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，本地翻译使用 Argos 模型与 CTranslate2。

## 权限及限制

使用 `activeTab` / `scripting` 在用户点击后临时注入字幕，`tabCapture` 捕获标签页声音，`offscreen` 持续处理，`nativeMessaging` 自动启动本机助手。保留 localhost 接口权限，没有添加读取所有网站的 `<all_urls>` 权限。Chrome 设置页、扩展商店等受限页不支持。

捕获的是整个标签页的声音，可能包括广告和通知；不捕获其他标签页、麦克风或桌面应用。跨域 iframe 播放器不一定能读取暂停和进度，全屏适配仍需逐站验收。不绕过 DRM、付费、登录或浏览器保护。

队列有界，落后时追赶最新音频并显示跳过更新数量，因此较慢电脑可能漏字。显示的“处理耗时”仅是识别请求的 CPU 处理时间，**不是声音到字幕的端到端延迟**。英语小模型在测试录音开头出现过误识别，不能据速度结果宣称准确率优于 Whisper。识别和翻译都可能出错。

实时 PCM、最近字幕和翻译任务在内存中短暂保留，不保存完整直播录音或逐字稿；现有同步模式的本地缓存机制保留。模型下载需要访问官方模型站点。没有新增云端识别或翻译 API。

## 测试与开发

详见 TEST-REPORT.md。源码及 Logo MIT；runtime、依赖和模型各自保留许可证。安装器未数字签名，商业发行前仍需许可及实际机器验收。

`native/build_windows.py` 可用已有许可 runtime ZIP 与展开的 sherpa Windows wheels 构建完整安装器。基础 runtime 包含 Python 3.11、requirements、翻译 tokenizer 依赖及 Deno；用户无需安装这些依赖。源码分布不含私有令牌、用户录音或模型权重。
