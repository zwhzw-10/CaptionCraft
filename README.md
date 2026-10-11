# 字幕翻译生成 · CaptionCraft

![Logo](Logo.png)

面向 Windows / Chrome 的本地 YouTube 字幕与可选翻译工具。当前为 **0.6.0 测试版**，尚未上架 Chrome 商店。

## 下载和使用

普通用户到本仓库右侧的 **Releases** 下载：

- `CaptionCraft-Assistant-Setup-v0.6.0.exe`：Windows 字幕助手，约 150 MB。
- `CaptionCraft-Extension-v0.6.0.zip`：Chrome 插件。

1. 运行助手安装器，点击安装，保留默认扩展 ID。
2. 全部解压插件 ZIP 到长期保留的目录。
3. Chrome 打开 `chrome://extensions`，开启开发者模式，选择“加载未打包的扩展程序”，加载解压的文件夹。
4. 刷新 YouTube 视频，打开插件，选择语言和显示方式，点击生成字幕。

助手内置 Python 和依赖，无需另装 Python、输入命令、粘贴令牌或运行 Start.cmd。首次使用需要下载识别模型；翻译模型按需下载。当前安装器未签名，Windows 可能显示未知发布者。测试版仅支持 Windows x64。

## 功能

- 原文语言：英语、日语、法语、西班牙语、韩语、俄语。
- 自由选择翻译目标，额外支持中文；仅原文、双语或仅译文。
- 优先现有字幕，否则下载音频后分段识别；也支持导入音频。
- 七种设置界面，字号、文字/背景透明度、背景颜色、字幕拖动和 SRT 导出。
- 助手自动启动和连接，空闲约五分钟后退出；模型和数据与程序分开保存。

## 当前限制

本版仍先完成音频下载，再分段识别。准备好的字幕按视频时间显示；未准备位置会暂停，请等待后自行播放。实时备用只支持原文并有延迟。YouTube 获取可能失败，识别可能错字，本地翻译可能误译。部分翻译经英语中转，不保证所有语言准确度。视频上限三小时，导入文件上限 200 MB。没有绕过登录、付费或 DRM。

建议 64 位 Windows 10/11、至少 8 GB 内存及数 GB 磁盘空间。识别和翻译在本机执行，但获取在线视频和首次下载模型需要网络。

## 开发与后续更新

源码目录：`extension` 为浏览器插件，`helper` 为识别/翻译服务，`native` 为原生桥接和 Windows 安装器，`shared` 为语言配置，`tests` 为回归测试。

`shared/languages.json` 统一定义原文和目标语言。新增语言还需要相应模型、翻译路线、界面文案和实际质量验收。升级助手保留 Data，不要求用户重新安装 Python。

Windows 构建步骤见 [native/BUILD.md](native/BUILD.md)。源码中的 Install/Start 脚本为旧开发入口，普通用户请使用 Releases 安装器。

在安装了 helper/requirements.txt 依赖的 Windows Python 环境执行：

```powershell
python -m unittest discover -s tests -p "test_*.py"
node tests/test_native_client.cjs
node tests/test_background.cjs
node tests/test_lifecycle.cjs
node tests/test_audio.cjs
node tests/test_captions.cjs
node tests/test_timeline.cjs
```

模型实测需另行下载模型；回归测试不自动下载模型。完整测试范围和未验收事项见 [TEST-REPORT.md](TEST-REPORT.md)。

## 隐私、许可和反馈

源码与 Logo 使用 [MIT](LICENSE)。依赖和模型遵循各自许可；本仓库不包含模型、个人令牌、字幕缓存和运行环境。隐私说明见 [PRIVACY.md](PRIVACY.md)。商业发行/商店发布前事项见 [PUBLISHING.md](PUBLISHING.md)。

问题请提交 GitHub Issue，说明 Windows/Chrome 版本、插件版本和复现步骤。截图或日志分享前隐藏个人文件路径及私有内容，不要提交配对令牌。
