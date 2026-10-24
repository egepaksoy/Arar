using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Setup {
    static string InstallRoot {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Arar"); }
    }

    [STAThread]
    static int Main(string[] args) {
        if (args.Length == 2 && args[0] == "--extract") {
            try { Extract(args[1]); return 0; }
            catch (Exception ex) { File.WriteAllText(args[1] + ".error.txt", ex.ToString()); return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Form form = new Form { Text = "Arar • Çevrimdışı Kurulum", ClientSize = new Size(570, 320),
            StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false, Font = new Font("Segoe UI", 10), BackColor = Color.White };
        Label title = new Label { Text = "Arar kurulumu", Font = new Font("Segoe UI", 20, FontStyle.Bold),
            AutoSize = true, Location = new Point(24, 22) };
        Label description = new Label { Text = "Python ve gerekli kütüphaneler pakete dahildir.\nKurulum ve uygulama için internet gerekmez.",
            Location = new Point(26, 76), Size = new Size(520, 52) };
        Label location = new Label { Text = "Kurulum konumu:\n" + InstallRoot, Location = new Point(26, 142), Size = new Size(520, 54) };
        CheckBox desktop = new CheckBox { Text = "Masaüstü kısayolu oluştur", Checked = true,
            AutoSize = true, Location = new Point(26, 207) };
        Label status = new Label { Text = "Mevcut Arar pencerelerini kurulumdan önce kapatın.",
            Location = new Point(26, 244), Size = new Size(340, 54) };
        Button install = new Button { Text = "Kur", Location = new Point(404, 252), Size = new Size(140, 44),
            BackColor = Color.FromArgb(8, 127, 140), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
        bool working = false, complete = false;
        form.FormClosing += delegate(object sender, FormClosingEventArgs e) { if (working) e.Cancel = true; };
        install.Click += async delegate {
            if (complete) { form.Close(); return; }
            working = true; install.Enabled = false; desktop.Enabled = false; status.Text = "Dosyalar kuruluyor…";
            bool shortcut = desktop.Checked;
            try {
                await Task.Run(delegate { Install(shortcut); });
                complete = true; install.Text = "Kapat";
                status.Text = "Kurulum tamamlandı. Arar’ı kısayolundan açabilirsiniz.";
            } catch (Exception ex) {
                status.Text = "Kurulum tamamlanamadı.";
                MessageBox.Show(form, ex.Message, "Arar kurulumu", MessageBoxButtons.OK, MessageBoxIcon.Error);
            } finally { working = false; install.Enabled = true; }
        };
        form.Controls.AddRange(new Control[] { title, description, location, desktop, status, install });
        Application.Run(form);
        return 0;
    }

    static void Extract(string destination) {
        destination = Path.GetFullPath(destination);
        if (Directory.Exists(destination) && Directory.GetFileSystemEntries(destination).Length != 0)
            throw new IOException("Çıkarma klasörü boş olmalıdır.");
        Directory.CreateDirectory(destination);
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Arar.Payload"))
        using (ZipArchive zip = new ZipArchive(resource, ZipArchiveMode.Read)) {
            foreach (ZipArchiveEntry entry in zip.Entries) {
                string target = Path.GetFullPath(Path.Combine(destination, entry.FullName));
                if (!target.StartsWith(destination + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new IOException("Geçersiz paket dosyası yolu.");
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (Stream input = entry.Open())
                using (Stream output = new FileStream(target, FileMode.CreateNew)) input.CopyTo(output);
            }
        }
    }

    static void Install(bool desktop) {
        Directory.CreateDirectory(InstallRoot);
        // Prevent concurrent installers and fail before modifying a running runtime.
        using (FileStream installLock = new FileStream(Path.Combine(InstallRoot, "install.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) {
            string dll = Path.Combine(InstallRoot, "runtime", "python312.dll");
            if (File.Exists(dll)) {
                try { using (FileStream check = new FileStream(dll, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) {} }
                catch (IOException) { throw new IOException("Arar çalışıyor. Pencereyi kapatıp kurulumu tekrar deneyin."); }
            }
            string stage = Path.Combine(Path.GetTempPath(), "Arar-" + Guid.NewGuid().ToString("N"));
            try {
                Extract(stage);
                foreach (string file in Directory.GetFiles(stage, "*", SearchOption.AllDirectories)) {
                    string relative = file.Substring(stage.Length + 1);
                    string target = Path.Combine(InstallRoot, relative);
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Copy(file, target, true);
                }
                string programs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Arar");
                Directory.CreateDirectory(programs);
                Shortcut(Path.Combine(programs, "Arar.lnk"));
                if (desktop) Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Arar.lnk"));
                JavaScriptSerializer json = new JavaScriptSerializer();
                Dictionary<string, object> manifest = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(InstallRoot, "installed_files.json")));
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\Arar")) {
                    key.SetValue("DisplayName", "Arar"); key.SetValue("DisplayVersion", manifest["version"].ToString());
                    key.SetValue("Publisher", "Arar"); key.SetValue("InstallLocation", InstallRoot);
                    key.SetValue("UninstallString", "\"" + Environment.GetEnvironmentVariable("ComSpec") + "\" /c \"\"" + Path.Combine(InstallRoot, "uninstall.cmd") + "\"\"");
                    key.SetValue("NoModify", 1); key.SetValue("NoRepair", 1);
                }
            } finally { if (Directory.Exists(stage)) Directory.Delete(stage, true); }
        }
    }

    static void Shortcut(string path) {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
        Type type = shortcut.GetType();
        type.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { Path.Combine(InstallRoot, "runtime", "pythonw.exe") });
        type.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { "-S -B \"" + Path.Combine(InstallRoot, "app", "main.py") + "\"" });
        type.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { Path.Combine(InstallRoot, "app") });
        type.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }
}
