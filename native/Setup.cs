using System;
using System.ComponentModel;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using Microsoft.Win32;

class Setup:Form {
 const string Version="0.6.0";
 const string DefaultId="__EXTENSION_ID__";
 const string Host="com.captioncraft.assistant";
 const string RegistryHost=@"Software\Google\Chrome\NativeMessagingHosts\com.captioncraft.assistant";
 const string RegistryUninstall=@"Software\Microsoft\Windows\CurrentVersion\Uninstall\CaptionCraftAssistant";
 readonly string home=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CaptionCraft");
 readonly bool zh=System.Globalization.CultureInfo.CurrentUICulture.Name.StartsWith("zh");
 Label notice;TextBox id;ProgressBar progress;Button install;CheckBox deleteData;bool completed=false;
 string T(string cn,string en){return zh?cn:en;}
 Setup(bool uninstall){
  Text=T("字幕翻译生成 · 字幕助手","CaptionCraft Assistant");ClientSize=new Size(590,310);StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;
  Font=new Font("Segoe UI",10);
  var title=new Label{Text=T("字幕助手 "+Version,"Subtitle Assistant "+Version),Location=new Point(25,22),AutoSize=true,Font=new Font("Segoe UI",17,FontStyle.Bold)};Controls.Add(title);
  notice=new Label{Text=T("只需安装一次，无需 Python 或黑色窗口。\n首次使用会下载识别模型；翻译模型按需下载。","Install once. No separate Python installation or terminal needed.\nModels download on first use; translation models download as needed."),Location=new Point(25,70),Size=new Size(540,65)};Controls.Add(notice);
  Controls.Add(new Label{Text=T("扩展 ID（已填好，通常无需修改）","Extension ID (preset; usually no change needed)"),Location=new Point(25,143),AutoSize=true});
  id=new TextBox{Text=DefaultId,Location=new Point(25,169),Width=535};Controls.Add(id);
  progress=new ProgressBar{Location=new Point(25,211),Size=new Size(535,16)};Controls.Add(progress);
  install=new Button{Text=uninstall?T("卸载助手","Uninstall"):T("安装 / 更新助手","Install / update"),Location=new Point(375,248),Size=new Size(185,38)};Controls.Add(install);
  deleteData=new CheckBox{Text=T("同时删除模型和字幕缓存","Also delete models and captions"),Location=new Point(25,250),AutoSize=true,Visible=uninstall};Controls.Add(deleteData);
  install.Click+=(s,e)=>{
   if(completed){Close();return;}
   if(!uninstall&&!Regex.IsMatch(id.Text.Trim(),"^[a-p]{32}$")){MessageBox.Show(T("扩展 ID 需要 32 个 a–p 字母。","Extension ID must contain 32 letters a–p."));return;}
   install.Enabled=false;id.Enabled=false;
   var worker=new BackgroundWorker{WorkerReportsProgress=true};
   string extensionId=id.Text.Trim();bool erase=deleteData.Checked;
   worker.DoWork+=(a,b)=>{if(uninstall)Uninstall(erase);else Install(extensionId,worker);};
   worker.ProgressChanged+=(a,b)=>{progress.Value=Math.Min(100,b.ProgressPercentage);notice.Text=(string)b.UserState;};
   worker.RunWorkerCompleted+=(a,b)=>{
    if(b.Error!=null){notice.Text=T("操作失败：","Operation failed: ")+b.Error.Message;install.Enabled=true;id.Enabled=true;return;}
    progress.Value=100;notice.Text=uninstall?T("助手已卸载。","Assistant removed."):T("安装完成。重新加载 Chrome 插件，刷新视频即可使用。\n不需要运行 Start.cmd。","Installed. Reload the Chrome extension and refresh the video.\nYou do not need Start.cmd.");
    completed=true;install.Text=T("关闭","Close");install.Enabled=true;
   };worker.RunWorkerAsync();
  };
 }
 void Install(string extensionId,BackgroundWorker worker){
  Directory.CreateDirectory(home);
  string app=Path.Combine(home,"app-"+Version);
  // Reinstallation must not overwrite an executable currently being used.
  if(Directory.Exists(app))app+="-"+DateTime.Now.ToString("yyyyMMddHHmmssfff");
  Directory.CreateDirectory(app);string prefix=Path.GetFullPath(app)+Path.DirectorySeparatorChar;
  using(Stream resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")){
   if(resource==null)throw new Exception("Installer payload missing.");
   using(var zip=new ZipArchive(resource,ZipArchiveMode.Read)){
    long total=0,done=0;foreach(var entry in zip.Entries)total+=entry.Length;
    foreach(var entry in zip.Entries){
     string destination=Path.GetFullPath(Path.Combine(app,entry.FullName));
     if(!destination.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new Exception("Unsafe payload path.");
     if(entry.FullName.EndsWith("/")){Directory.CreateDirectory(destination);continue;}
     Directory.CreateDirectory(Path.GetDirectoryName(destination));entry.ExtractToFile(destination,true);done+=entry.Length;
     worker.ReportProgress((int)(done*80/Math.Max(1,total)),T("正在安装运行环境… ","Installing runtime… ")+done/1048576+" MB");
    }
   }
  }
  // Model migration copies only known models, never credentials or cached transcripts.
  string legacy=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),@"新建文件夹\Local-English-Captions-MVP\local-english-captions\models");
  string models=Path.Combine(home,"Data","models");
  if(Directory.Exists(legacy)&&!Directory.Exists(models)){
   worker.ReportProgress(85,T("正在保留已有识别和翻译模型…","Preserving existing models…"));CopyTree(legacy,models);
  }
  string executable=Path.Combine(app,"CaptionCraftHost.exe");
  string manifest=Path.Combine(app,"native-host.json");
  string body="{\"name\":\""+Host+"\",\"description\":\"CaptionCraft Assistant\",\"path\":\""+executable.Replace("\\","\\\\")+"\",\"type\":\"stdio\",\"allowed_origins\":[\"chrome-extension://"+extensionId+"/\"]}";
  File.WriteAllText(manifest,body,new UTF8Encoding(false));
  using(var key=Registry.CurrentUser.CreateSubKey(RegistryHost))key.SetValue("",manifest);
  string manager=Path.Combine(home,"CaptionCraftMaintenance.exe");
  // Maintenance is a small executable, without an embedded installer payload.
  File.Copy(Path.Combine(app,"CaptionCraftMaintenance.exe"),manager,true);
  using(var key=Registry.CurrentUser.CreateSubKey(RegistryUninstall)){
   key.SetValue("DisplayName","CaptionCraft Assistant");key.SetValue("DisplayVersion",Version);
   key.SetValue("Publisher","CaptionCraft");key.SetValue("UninstallString","\""+manager+"\" --uninstall");
   key.SetValue("InstallLocation",home);key.SetValue("NoModify",1);key.SetValue("NoRepair",1);
  }
  worker.ReportProgress(100,T("安装完成","Installed"));
 }
 static void CopyTree(string source,string target){
  Directory.CreateDirectory(target);
  foreach(string file in Directory.GetFiles(source))File.Copy(file,Path.Combine(target,Path.GetFileName(file)),false);
  foreach(string dir in Directory.GetDirectories(source)){
   if((File.GetAttributes(dir)&FileAttributes.ReparsePoint)!=0)continue;
   CopyTree(dir,Path.Combine(target,Path.GetFileName(dir)));
  }
 }
 void Uninstall(bool erase){
  string parent=Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData))+Path.DirectorySeparatorChar;
  string resolved=Path.GetFullPath(home);
  if(!resolved.StartsWith(parent,StringComparison.OrdinalIgnoreCase)||Path.GetFileName(resolved)!="CaptionCraft")throw new Exception("Unsafe uninstall target.");
  // Only remove this product's registration; never another product's registry keys.
  using(var key=Registry.CurrentUser.OpenSubKey(RegistryHost)){
   string registered=key==null?null:key.GetValue("") as string;
   if(registered!=null&&!Path.GetFullPath(registered).StartsWith(resolved+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Host registration points outside this installation.");
  }
  // User closes Chrome first. Never terminate unrelated processes.
  foreach(string dir in Directory.GetDirectories(home,"app-*")){
   if(!Path.GetFullPath(dir).StartsWith(resolved+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||(File.GetAttributes(dir)&FileAttributes.ReparsePoint)!=0)throw new Exception("Unsafe application directory.");
   Directory.Delete(dir,true);
  }
  if(Directory.Exists(Path.Combine(home,"Data"))&&(File.GetAttributes(Path.Combine(home,"Data"))&FileAttributes.ReparsePoint)!=0)throw new Exception("Unsafe data directory.");
  if(erase&&Directory.Exists(Path.Combine(home,"Data")))Directory.Delete(Path.Combine(home,"Data"),true);
  Registry.CurrentUser.DeleteSubKeyTree(RegistryHost,false);Registry.CurrentUser.DeleteSubKeyTree(RegistryUninstall,false);
 }
 [STAThread]static void Main(string[] args){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Setup(Array.IndexOf(args,"--uninstall")>=0||Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")==null));}
}
