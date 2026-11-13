
using System;
using System.IO;
using System.Text;
using System.Diagnostics;
using System.Windows.Forms;
class ModixLauncher {
  static string Quote(string value) {
    var b=new StringBuilder("\""); int slashes=0;
    foreach(char c in value) {
      if(c=='\\') { slashes++; continue; }
      if(c=='\"') { b.Append('\\',slashes*2+1); b.Append(c); slashes=0; continue; }
      b.Append('\\',slashes); slashes=0; b.Append(c);
    }
    b.Append('\\',slashes*2); b.Append('\"'); return b.ToString();
  }
  [STAThread] static int Main(string[] args) {
    try {
      string folder=AppDomain.CurrentDomain.BaseDirectory;
      string python=Path.Combine(folder,"_runtime","pythonw.exe");
      string script=Path.Combine(folder,"cliente.py");
      if(!File.Exists(python)||!File.Exists(script)) {
        MessageBox.Show("Extrae la carpeta completa, incluido _runtime, antes de abrir MODIX.","MODIX 11"); return 2;
      }
      var command=new StringBuilder(Quote(script));
      foreach(string arg in args) command.Append(" ").Append(Quote(arg));
      var start=new ProcessStartInfo(python,command.ToString());
      start.WorkingDirectory=folder; start.UseShellExecute=false; start.CreateNoWindow=true;
      start.EnvironmentVariables.Remove("PYTHONHOME");start.EnvironmentVariables.Remove("PYTHONPATH");
      start.EnvironmentVariables["PYTHONNOUSERSITE"]="1";
      using(var process=Process.Start(start)) { process.WaitForExit(); return process.ExitCode; }
    } catch(Exception e) {MessageBox.Show(e.Message,"MODIX 11 · Error de inicio");return 1;}
  }
}
