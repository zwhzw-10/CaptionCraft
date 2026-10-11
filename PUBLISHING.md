# 发布前事项

先以免费 Windows 测试版验证。Chrome 商店只上传 Extension ZIP，助手安装器单独提供。现在未发布到商店或 GitHub。

商店赋予的最终扩展 ID 必须写入助手 allowed_origins，并更新 native/build_windows.py 所用扩展公钥及安装器默认 ID；不能给所有扩展开放访问。安装器默认已配置本测试版固定 ID。

正式发布需要：干净机器验收、发行代码签名、在线隐私政策、nativeMessaging/tabCapture/localhost 权限说明、用户首次安装教程、模型许可审核。安装器免费本地运行并不意味着商店开发者注册免费。

源码和 Logo MIT；第三方包各遵循其许可证。Python LICENSE、Deno LICENSE、yt-dlp LICENSE 和依赖 dist-info 内许可文件随助手保留。Argos 模型按需下载，不打包，但仍需审核各模型包的商业条款和数据来源。公开源码不要上传 Data、令牌、日志、缓存和模型。

https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
https://developer.chrome.com/docs/webstore/register/
https://developer.chrome.com/docs/webstore/program-policies/user-data-faq
