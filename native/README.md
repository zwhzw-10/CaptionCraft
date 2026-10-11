# Windows assistant architecture

Chrome connects to `com.captioncraft.assistant` using nativeMessaging. The installer registers an HKCU host manifest with explicit allowed_origins; the host independently checks its caller. A stable public extension key gives the unpacked test build a consistent extension ID. Replace the release ID/key with the Chrome store's assigned values before releasing there; regenerate the installer. Do not enable arbitrary extension origins.

CaptionCraftHost.exe is a small .NET Framework 4.x binary bridge. It forwards framed messages to the bundled isolated Python runtime with explicit flushes. host.py starts only its own child recognizer on an allocated loopback port, with a persistent private token in Data/helper/config.json. The token reaches only approved extension pages via the service worker, never YouTube content scripts. Audio uses loopback HTTP rather than native messages because native responses have size limits.

The port remains connected while the extension works. Native bridge EOF shuts down its own recognizer. The service worker disconnects after five minutes without API use; prepared subtitles remain in the webpage. Reconnect resets a failed host. This is not a Windows auto-start service or scheduled task.

Per-user app directory: `%LOCALAPPDATA%/CaptionCraft/app-0.6.0`. Models/cache/settings: `%LOCALAPPDATA%/CaptionCraft/Data`. App updates use a new version directory and preserve Data. Reinstallations use a unique directory to avoid overwriting running binaries. Old app directories can be removed with the uninstaller after Chrome closes; they are not silently deleted during an update.

shared/languages.json is the source/target catalog. The build generates extension/languages.js from it. UI translation dictionaries, recognition support, translation routes and quality tests still need updating for each added language. Adding a code alone does not guarantee model support.

The installer uses Windows Forms, installs without administrator rights, copies a relocatable runtime and registers an Apps uninstall entry. It can migrate models from the known old test installation; credentials and cached transcripts are not copied. No arbitrary command execution or path is accepted from the extension.

Unsigned test installer: no publisher certificate is included. Distribution signing, clean-machine testing, license review and the final store ID remain release work. Runtime bundling contains Python, .NET bridge, ASR/translation dependencies and Deno, but no model weights.
