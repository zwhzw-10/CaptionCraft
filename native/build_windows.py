from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile,base64
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--python-root',required=True);parser.add_argument('--site-packages',required=True);parser.add_argument('--deno',required=True);parser.add_argument('--build-dir',required=True);args=parser.parse_args()
BUILD=Path(args.build_dir).resolve();BUILD.mkdir(parents=True,exist_ok=True)
APP=BUILD/'payload';APP.mkdir(exist_ok=True)
BASE=Path(args.python_root)
PACKAGES=Path(args.site_packages)
CSC=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
DOTNET=CSC.parent
public_file=ROOT/'native/extension-public-key.txt'
if not public_file.exists():
 result=subprocess.run(['node','-e',"const c=require('crypto');console.log(c.generateKeyPairSync('rsa',{modulusLength:2048,publicKeyEncoding:{type:'spki',format:'der'},privateKeyEncoding:{type:'pkcs8',format:'der'}}).publicKey.toString('base64'));"],capture_output=True,text=True,check=True)
 public_file.write_text(result.stdout.strip())
public=public_file.read_text().strip();digest=hashlib.sha256(base64.b64decode(public)).hexdigest()[:32]
extension_id=''.join(chr(ord('a')+int(c,16)) for c in digest)
m=json.loads((ROOT/'extension/manifest.json').read_text());m['key']=public;m['version']='0.6.0'
m['permissions']=list(dict.fromkeys(m['permissions']+['nativeMessaging','alarms']))
m['host_permissions']=['http://127.0.0.1/*']
m['content_security_policy']['extension_pages']="script-src 'self'; object-src 'self'; connect-src http://127.0.0.1:*"
(ROOT/'extension/manifest.json').write_text(json.dumps(m,indent=2,ensure_ascii=False))
(ROOT/'EXTENSION-ID.txt').write_text(extension_id+'\n')
registry=json.loads((ROOT/'shared/languages.json').read_text(encoding='utf8'))
(ROOT/'extension/languages.js').write_text('globalThis.CAPTION_LANGUAGES = '+json.dumps(registry,ensure_ascii=False)+';\n',encoding='utf8')
p=ROOT/'extension/popup.html';body=p.read_text(encoding='utf8').replace('0.5.1','0.6.0')
if '<details><summary data-i18n="pairing">' in body:
 start=body.index('<details><summary data-i18n="pairing">');end=body.index('</details>',start)+len('</details>')
 body=body[:start]+'<p class="hint" data-i18n="assistantHelp"></p><button id="assistant-retry" data-i18n="assistantRetry"></button>'+body[end:]
if 'src="languages.js"' not in body:body=body.replace('<script src="popup.js">','<script src="languages.js"></script><script src="popup.js">')
p.write_text(body,encoding='utf8')
# Localization overrides are versioned with the client, not hidden in the host.
localized={
'zh':['正在启动字幕助手；首次需要下载识别模型，请稍候…','请安装字幕助手，然后点击“重新连接”。无需安装 Python 或运行 Start.cmd。','助手准备超时。检查网络后重新连接；下载完成后无需再次下载。','无法连接字幕助手，请点击重新连接；仍失败时重新安装助手。','助手会自动启动，闲置后退出。语言和模型按需下载。','重新连接助手'],
'en':['Starting the assistant; first use downloads the recognition model…','Install the assistant, then reconnect. No Python or Start.cmd needed.','Assistant startup timed out. Check the network and reconnect.','Cannot connect to the assistant. Reconnect or reinstall it.','The assistant starts automatically and exits when idle. Models download as needed.','Reconnect assistant'],
'ja':['字幕アシスタントを起動中。初回はモデルをダウンロードします…','アシスタントをインストールして再接続してください。Python は不要です。','準備がタイムアウトしました。ネットワークを確認して再接続してください。','アシスタントに接続できません。再接続または再インストールしてください。','自動起動し、未使用時は終了します。モデルは必要に応じて取得します。','アシスタントに再接続'],
'fr':['Démarrage de l’assistant ; premier téléchargement du modèle…','Installez l’assistant puis reconnectez-le. Python n’est pas nécessaire.','Délai dépassé. Vérifiez le réseau puis reconnectez-vous.','Connexion impossible. Reconnectez ou réinstallez l’assistant.','Démarrage automatique et arrêt après inactivité. Modèles à la demande.','Reconnecter l’assistant'],
'es':['Iniciando el asistente; se descarga el modelo en el primer uso…','Instala el asistente y vuelve a conectar. No necesitas Python.','Se agotó el tiempo. Comprueba la red y vuelve a conectar.','No se puede conectar. Reconecta o reinstala el asistente.','Inicio automático y cierre tras inactividad. Modelos según necesidad.','Reconectar asistente'],
'ko':['자막 도우미 시작 중. 처음에는 모델을 다운로드합니다…','도우미를 설치한 후 다시 연결하세요. Python은 필요하지 않습니다.','준비 시간이 초과되었습니다. 네트워크를 확인하고 다시 연결하세요.','도우미에 연결할 수 없습니다. 다시 연결하거나 재설치하세요.','자동으로 시작하고 사용하지 않을 때 종료됩니다. 모델은 필요할 때 다운로드합니다.','도우미 다시 연결'],
'ru':['Запуск помощника; при первом использовании загружается модель…','Установите помощник и подключитесь снова. Python не нужен.','Время ожидания истекло. Проверьте сеть и подключитесь снова.','Нет соединения. Подключите или переустановите помощник.','Автоматический запуск и выход после простоя. Модели по необходимости.','Подключить помощник']}
overrides={lang:dict(zip(['assistantLoading','assistantMissing','assistantTimeout','unreachable','assistantHelp','assistantRetry'],values)) for lang,values in localized.items()}
for lang,value in {'zh':'查看助手日志','en':'Assistant diagnostics','ja':'アシスタント診断','fr':'Diagnostic de l’assistant','es':'Diagnóstico del asistente','ko':'도우미 진단','ru':'Диагностика помощника'}.items():overrides[lang]['assistantDiagnostics']=value
p=ROOT/'extension/i18n.js';body=p.read_text(encoding='utf8');marker='// Assistant localization 0.6\n'
if marker in body:body=body[:body.index(marker)]
body+='\n'+marker+'for(const [lang,values] of Object.entries('+json.dumps(overrides,ensure_ascii=False)+')) Object.assign(UI_MESSAGES[lang],values);\n'
p.write_text(body,encoding='utf8')
# Copy a relocatable Windows runtime. Users do not install Python themselves.
runtime=APP/'runtime';runtime.mkdir(exist_ok=True)
def ignored(folder,names):return [n for n in names if n in ('__pycache__','test','tests','idlelib','ensurepip','tkinter','site-packages') or n.endswith('.pyc')]
for name in ['python.exe','python3.dll','python311.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:shutil.copy2(BASE/name,runtime/name)
shutil.copytree(BASE/'DLLs',runtime/'DLLs',dirs_exist_ok=True)
shutil.copytree(BASE/'Lib',runtime/'Lib',dirs_exist_ok=True,ignore=ignored)
packages=runtime/'Lib/site-packages';packages.mkdir(exist_ok=True)
for src in PACKAGES.iterdir():
 if src.name in ('__pycache__','pip','setuptools','pkg_resources','_distutils_hack') or src.name.startswith(('pip-','setuptools-')) or src.suffix in ('.pyc','.pth'):continue
 if src.is_dir():shutil.copytree(src,packages/src.name,dirs_exist_ok=True,ignore=lambda f,n:[v for v in n if v=='__pycache__' or v.endswith('.pyc')])
 else:shutil.copy2(src,packages/src.name)
(runtime/'python311._pth').write_text('DLLs\nLib\nLib/site-packages\nimport site\n')
for name in ['helper','shared','native']:
 shutil.copytree(ROOT/name,APP/name,dirs_exist_ok=True,ignore=lambda f,n:[x for x in n if x in ('__pycache__','config.json') or x.endswith('.pyc')])
deno=APP/'tools/deno';deno.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(args.deno),deno/'deno.exe')
shutil.copy2(ROOT/'LICENSE',APP/'LICENSE')
setup=BUILD/'Setup.cs';setup.write_text((ROOT/'native/Setup.cs').read_text(encoding='utf8').replace('__EXTENSION_ID__',extension_id),encoding='utf-8-sig')
refs=['/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:'+str(DOTNET/'System.IO.Compression.dll'),'/r:'+str(DOTNET/'System.IO.Compression.FileSystem.dll')]
subprocess.run([str(CSC),'/nologo','/target:exe','/platform:x64','/out:'+str(APP/'CaptionCraftHost.exe'),str(ROOT/'native/Bridge.cs')],check=True)
subprocess.run([str(CSC),'/nologo','/target:winexe','/platform:x64','/out:'+str(APP/'CaptionCraftMaintenance.exe'),*refs,str(setup)],check=True)
payload=BUILD/'payload.zip'
with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for file in sorted(APP.rglob('*')):
  if file.is_file():z.write(file,file.relative_to(APP).as_posix())
installer=ROOT.parent/'CaptionCraft-Assistant-Setup-v0.6.0.exe'
subprocess.run([str(CSC),'/nologo','/target:winexe','/platform:x64','/out:'+str(installer),*refs,'/resource:'+str(payload)+',payload.zip',str(setup)],check=True)
for name,prefix,folder in [('CaptionCraft-Extension-v0.6.0.zip','',ROOT/'extension'),('CaptionCraft-Source-v0.6.0.zip','captioncraft/',ROOT)]:
 with zipfile.ZipFile(ROOT.parent/name,'w',zipfile.ZIP_DEFLATED) as z:
  for file in sorted(folder.rglob('*')):
   rel=file.relative_to(folder)
   if not file.is_file() or any(p in ('__pycache__','.venv','models','.cache','.backup') for p in rel.parts) or rel.as_posix() in ('helper/config.json','Local-Pairing.txt') or file.suffix in ('.pyc','.log'):continue
   z.write(file,prefix+rel.as_posix())
 print(name)
print('Extension ID:',extension_id)
print('Installer bytes:',installer.stat().st_size)

