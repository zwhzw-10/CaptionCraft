# Rebuilding Windows installer

Use Python 3.11 64-bit, a site-packages directory containing helper/requirements.txt and yt-dlp[default], verified official Deno for Windows, Node.js, and Windows .NET Framework 4.x C# compiler. All inputs must be trusted and have redistributable licenses.

Run native/build_windows.py with --python-root, --site-packages, --deno, --build-dir. It packages a relocatable runtime, compiles the binary bridge and Windows Forms installer, embeds a ZIP payload and creates source/extension ZIPs. It preserves native/extension-public-key.txt for a stable unpacked extension ID. This public key is not a signing private key. Do not generate a different public key for every update.

The runtime is platform-specific. Build and test on Windows x64; do not claim macOS/Linux support. Revalidate native pipe flushes and a real bundled runtime after dependency upgrades. Store production ID must replace the test ID before distribution.
