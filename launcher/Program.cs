using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Net.Sockets;
using System.Text.Json;

namespace ResumeBranch.Launcher;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Any(argument => string.Equals(argument, "--stop", StringComparison.OrdinalIgnoreCase)))
        {
            AppCoordinator.StopInstalledServices();
            return;
        }

        ApplicationConfiguration.Initialize();
        Application.Run(new SplashForm());
    }
}

internal sealed class SplashForm : Form
{
    private readonly AppCoordinator coordinator = new();

    public SplashForm()
    {
        AutoScaleMode = AutoScaleMode.Dpi;
        BackColor = Color.FromArgb(48, 48, 48);
        ClientSize = new Size(338, 150);
        FormBorderStyle = FormBorderStyle.None;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        Text = "ResumeBranch";

        Shown += OnShown;
        Paint += PaintBrand;
    }

    private async void OnShown(object? sender, EventArgs e)
    {
        try
        {
            await Task.Delay(120);
            await coordinator.StartAsync();
            coordinator.OpenBrowser();
            Close();
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                this,
                $"ResumeBranch 启动失败。\n\n{exception.Message}\n\n日志目录：\n{coordinator.LogDirectory}",
                "ResumeBranch",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            Close();
        }
    }

    private static void PaintBrand(object? sender, PaintEventArgs e)
    {
        if (sender is not Form form)
        {
            return;
        }

        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        e.Graphics.Clear(form.BackColor);

        const float scale = 1.4f;
        const float left = 40f;
        const float top = 35f;
        using var palePen = new Pen(Color.FromArgb(238, 241, 245), 3.4f)
        {
            StartCap = LineCap.Round,
            EndCap = LineCap.Round,
            LineJoin = LineJoin.Round
        };
        using var bluePen = new Pen(Color.FromArgb(77, 156, 255), 3.6f)
        {
            StartCap = LineCap.Round,
            EndCap = LineCap.Round,
            LineJoin = LineJoin.Round
        };

        PointF P(float x, float y) => new(left + x * scale, top + y * scale);
        using var documentPath = new GraphicsPath();
        documentPath.StartFigure();
        documentPath.AddBezier(P(29.8f, 42), P(28.8f, 42.35f), P(27.75f, 42.5f), P(26.5f, 42.5f));
        documentPath.AddLine(P(26.5f, 42.5f), P(17, 42.5f));
        documentPath.AddBezier(P(17, 42.5f), P(14.8f, 42.5f), P(13, 40.7f), P(13, 38.5f));
        documentPath.AddLine(P(13, 38.5f), P(13, 8));
        documentPath.AddBezier(P(13, 8), P(13, 5.8f), P(14.8f, 4), P(17, 4));
        documentPath.AddLine(P(17, 4), P(42, 4));
        documentPath.AddLine(P(42, 4), P(51, 13));
        documentPath.AddLine(P(51, 13), P(51, 38.5f));
        documentPath.AddBezier(P(51, 38.5f), P(51, 40.7f), P(49.2f, 42.5f), P(47, 42.5f));
        documentPath.AddLine(P(47, 42.5f), P(37.5f, 42.5f));
        documentPath.AddBezier(P(37.5f, 42.5f), P(36.25f, 42.5f), P(35.2f, 42.35f), P(34.2f, 42));
        e.Graphics.DrawPath(palePen, documentPath);
        e.Graphics.DrawLines(palePen, new[] { P(42, 4), P(42, 13), P(51, 13) });
        e.Graphics.DrawLine(palePen, P(22, 20), P(40, 20));
        e.Graphics.DrawLine(palePen, P(22, 27), P(38, 27));
        using var blueBranch = new GraphicsPath();
        blueBranch.AddBezier(P(27.8f, 50.8f), P(25.8f, 52.65f), P(24.1f, 54), P(22.1f, 54.8f));
        e.Graphics.DrawPath(bluePen, blueBranch);
        using var paleBranch = new GraphicsPath();
        paleBranch.AddBezier(P(36.2f, 50.8f), P(38.2f, 52.65f), P(39.9f, 54), P(41.9f, 54.8f));
        e.Graphics.DrawPath(palePen, paleBranch);
        e.Graphics.DrawEllipse(bluePen, left + (32 - 4.25f) * scale, top + (48 - 4.25f) * scale, 8.5f * scale, 8.5f * scale);
        e.Graphics.DrawEllipse(palePen, left + (18 - 3.75f) * scale, top + (57 - 3.75f) * scale, 7.5f * scale, 7.5f * scale);
        e.Graphics.DrawEllipse(palePen, left + (46 - 3.75f) * scale, top + (57 - 3.75f) * scale, 7.5f * scale, 7.5f * scale);

        using var brandFont = new Font("Georgia", 23f, FontStyle.Regular, GraphicsUnit.Pixel);
        using var brandBrush = new SolidBrush(Color.FromArgb(244, 244, 246));
        e.Graphics.DrawString("ResumeBranch", brandFont, brandBrush, 123f, 59f);

        using var accentBrush = new SolidBrush(Color.FromArgb(95, 143, 242));
        e.Graphics.FillRectangle(accentBrush, 0, form.ClientSize.Height - 2, form.ClientSize.Width, 2);
    }
}

internal sealed class AppCoordinator
{
    private const string FrontendUrl = "http://127.0.0.1:5173/";
    private const string BackendUrl = "http://127.0.0.1:8000";
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(3);

    private readonly string installRoot = Path.GetFullPath(AppContext.BaseDirectory);
    private readonly HttpClient httpClient = new(new SocketsHttpHandler { UseProxy = false })
    {
        Timeout = RequestTimeout
    };

    private string AppRoot => Path.Combine(installRoot, "app");
    private string RuntimeRoot => Path.Combine(installRoot, "runtime");
    public string LogDirectory => Path.Combine(AppRoot, ".local-run");
    private string NginxStateDirectory => Path.Combine(LogDirectory, "nginx");

    public async Task StartAsync()
    {
        ValidateInstallation();
        Directory.CreateDirectory(LogDirectory);

        if (!await IsBackendReadyAsync())
        {
            if (await IsPortOpenAsync(8000))
            {
                throw new InvalidOperationException("端口 8000 已被其他程序占用。");
            }

            StartBackend();
            if (!await WaitUntilAsync(IsBackendReadyAsync, TimeSpan.FromSeconds(50)))
            {
                throw new InvalidOperationException("本地后端未能正常启动。");
            }
        }

        if (!await IsFrontendReadyAsync())
        {
            if (await IsPortOpenAsync(5173))
            {
                throw new InvalidOperationException("端口 5173 已被其他程序占用。");
            }

            StartFrontendProxy();
            if (!await WaitUntilAsync(IsFrontendReadyAsync, TimeSpan.FromSeconds(25)))
            {
                throw new InvalidOperationException("本地页面未能正常启动。");
            }
        }
    }

    public void OpenBrowser()
    {
        Process.Start(new ProcessStartInfo(FrontendUrl) { UseShellExecute = true });
    }

    private void ValidateInstallation()
    {
        var requiredFiles = new[]
        {
            Path.Combine(RuntimeRoot, "python", "pythonw.exe"),
            Path.Combine(RuntimeRoot, "nginx", "nginx.exe"),
            Path.Combine(AppRoot, "scripts", "run_local_backend.py"),
            Path.Combine(AppRoot, "packaging", "run_installed_backend.py"),
            Path.Combine(AppRoot, "frontend", "dist", "index.html"),
            Path.Combine(installRoot, "resources", "nginx.local.conf.template")
        };

        var missing = requiredFiles.FirstOrDefault(path => !File.Exists(path));
        if (missing is not null)
        {
            throw new FileNotFoundException("安装文件不完整，请重新运行安装程序。", missing);
        }
    }

    private async Task<bool> IsBackendReadyAsync()
    {
        try
        {
            using var healthRequest = new HttpRequestMessage(HttpMethod.Post, $"{BackendUrl}/health");
            using var healthResponse = await httpClient.SendAsync(healthRequest);
            if (!healthResponse.IsSuccessStatusCode)
            {
                return false;
            }

            using var configResponse = await httpClient.GetAsync($"{BackendUrl}/app/config");
            if (!configResponse.IsSuccessStatusCode)
            {
                return false;
            }

            await using var stream = await configResponse.Content.ReadAsStreamAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            var root = document.RootElement;
            return root.TryGetProperty("app_mode", out var mode)
                && mode.GetString() == "local"
                && root.TryGetProperty("database_backend", out var database)
                && database.GetString() == "sqlite";
        }
        catch (HttpRequestException)
        {
            return false;
        }
        catch (TaskCanceledException)
        {
            return false;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private async Task<bool> IsFrontendReadyAsync()
    {
        try
        {
            using var response = await httpClient.GetAsync(FrontendUrl);
            if (!response.IsSuccessStatusCode)
            {
                return false;
            }

            var content = await response.Content.ReadAsStringAsync();
            return content.Contains("id=\"app\"", StringComparison.OrdinalIgnoreCase);
        }
        catch (HttpRequestException)
        {
            return false;
        }
        catch (TaskCanceledException)
        {
            return false;
        }
    }

    private void StartBackend()
    {
        var pythonRoot = Path.Combine(RuntimeRoot, "python");
        var popplerBin = FindPopplerBin();
        var chromium = Path.Combine(RuntimeRoot, "chromium", "chrome-headless-shell.exe");
        if (!File.Exists(chromium))
        {
            throw new FileNotFoundException("安装包中的 Chromium 不完整。", chromium);
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = Path.Combine(pythonRoot, "pythonw.exe"),
            Arguments = Quote(Path.Combine(AppRoot, "packaging", "run_installed_backend.py")),
            WorkingDirectory = AppRoot,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        startInfo.Environment["PATH"] = string.Join(
            Path.PathSeparator,
            new[] { pythonRoot, popplerBin, startInfo.Environment["PATH"] ?? string.Empty }
        );
        startInfo.Environment["PYTHONNOUSERSITE"] = "1";
        startInfo.Environment["RESUME_PDF_BROWSER"] = chromium;
        startInfo.Environment["POPPLER_PATH"] = popplerBin;

        if (Process.Start(startInfo) is null)
        {
            throw new InvalidOperationException("无法创建本地后端进程。");
        }
    }

    private void StartFrontendProxy()
    {
        Directory.CreateDirectory(NginxStateDirectory);
        Directory.CreateDirectory(Path.Combine(NginxStateDirectory, "logs"));
        Directory.CreateDirectory(Path.Combine(NginxStateDirectory, "temp", "client_body"));
        Directory.CreateDirectory(Path.Combine(NginxStateDirectory, "temp", "proxy"));

        var configPath = Path.Combine(NginxStateDirectory, "nginx.conf");
        var templatePath = Path.Combine(installRoot, "resources", "nginx.local.conf.template");
        var config = File.ReadAllText(templatePath)
            .Replace("{{FRONTEND_ROOT}}", NginxPath(Path.Combine(AppRoot, "frontend", "dist")), StringComparison.Ordinal)
            .Replace("{{MIME_TYPES}}", NginxPath(Path.Combine(RuntimeRoot, "nginx", "conf", "mime.types")), StringComparison.Ordinal)
            .Replace("{{STATE_ROOT}}", NginxPath(NginxStateDirectory), StringComparison.Ordinal);
        File.WriteAllText(configPath, config);

        var startInfo = new ProcessStartInfo
        {
            FileName = Path.Combine(RuntimeRoot, "nginx", "nginx.exe"),
            // Keep the Nginx command line ASCII-only. Its Windows build can
            // read Unicode paths from the UTF-8 config, but not from argv.
            Arguments = "-p . -c nginx.conf",
            WorkingDirectory = NginxStateDirectory,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        if (Process.Start(startInfo) is null)
        {
            throw new InvalidOperationException("无法创建本地页面进程。");
        }
    }

    private string FindPopplerBin()
    {
        var popplerRoot = Path.Combine(RuntimeRoot, "poppler");
        if (!Directory.Exists(popplerRoot))
        {
            throw new DirectoryNotFoundException("安装包中的 Poppler 不完整。");
        }

        var pdfInfo = Directory.EnumerateFiles(popplerRoot, "pdfinfo.exe", SearchOption.AllDirectories).FirstOrDefault();
        if (pdfInfo is null || !File.Exists(Path.Combine(Path.GetDirectoryName(pdfInfo)!, "pdftoppm.exe")))
        {
            throw new FileNotFoundException("安装包中的 Poppler 工具不完整。");
        }

        return Path.GetDirectoryName(pdfInfo)!;
    }

    private static async Task<bool> WaitUntilAsync(Func<Task<bool>> predicate, TimeSpan timeout)
    {
        var stopwatch = Stopwatch.StartNew();
        while (stopwatch.Elapsed < timeout)
        {
            if (await predicate())
            {
                return true;
            }
            await Task.Delay(500);
        }
        return false;
    }

    private static async Task<bool> IsPortOpenAsync(int port)
    {
        try
        {
            using var client = new TcpClient();
            using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
            await client.ConnectAsync("127.0.0.1", port, cancellation.Token);
            return true;
        }
        catch (Exception exception) when (exception is SocketException or OperationCanceledException)
        {
            return false;
        }
    }

    private static string Quote(string value) => $"\"{value.Replace("\"", "\\\"")}\"";
    private static string NginxPath(string value) => Path.GetFullPath(value).Replace('\\', '/');

    public static void StopInstalledServices()
    {
        var installRoot = Path.GetFullPath(AppContext.BaseDirectory);
        var appRoot = Path.Combine(installRoot, "app");
        var runtimeRoot = Path.Combine(installRoot, "runtime");
        var stateRoot = Path.Combine(appRoot, ".local-run", "nginx");
        var nginx = Path.Combine(runtimeRoot, "nginx", "nginx.exe");
        var nginxConfig = Path.Combine(stateRoot, "nginx.conf");
        var backend = Path.Combine(runtimeRoot, "python", "pythonw.exe");

        if (File.Exists(nginx) && File.Exists(nginxConfig))
        {
            try
            {
                using var process = Process.Start(new ProcessStartInfo
                {
                    FileName = nginx,
                    Arguments = "-p . -c nginx.conf -s quit",
                    WorkingDirectory = stateRoot,
                    UseShellExecute = false,
                    CreateNoWindow = true
                });
                process?.WaitForExit(5000);
            }
            catch
            {
                // Uninstall should continue even when the proxy is already stopped.
            }
        }

        // Nginx may leave worker processes behind after the graceful quit
        // signal. Wait briefly, then terminate only processes belonging to
        // this installation so runtime files are not left locked during uninstall.
        StopProcessesAtPath(nginx, TimeSpan.FromSeconds(5), forceTerminate: true);

        var pidFile = Path.Combine(appRoot, ".local-run", "backend.installed.pid");
        if (File.Exists(pidFile) && int.TryParse(File.ReadAllText(pidFile).Trim(), out var pid))
        {
            StopProcessById(pid, backend);
        }

        // Fall back to an exact executable-path match when the PID file was
        // removed during shutdown or was not written before an uninstall.
        StopProcessesAtPath(backend, TimeSpan.Zero, forceTerminate: true);
    }

    private static void StopProcessesAtPath(string expectedPath, TimeSpan gracefulTimeout, bool forceTerminate)
    {
        if (!File.Exists(expectedPath))
        {
            return;
        }

        var deadline = DateTime.UtcNow + gracefulTimeout;
        while (GetProcessIdsAtPath(expectedPath).Count > 0 && DateTime.UtcNow < deadline)
        {
            Thread.Sleep(100);
        }

        if (!forceTerminate)
        {
            return;
        }

        foreach (var processId in GetProcessIdsAtPath(expectedPath))
        {
            StopProcessById(processId, expectedPath);
        }
    }

    private static List<int> GetProcessIdsAtPath(string expectedPath)
    {
        var processName = Path.GetFileNameWithoutExtension(expectedPath);
        var processIds = new List<int>();
        foreach (var process in Process.GetProcessesByName(processName))
        {
            try
            {
                if (string.Equals(
                    Path.GetFullPath(process.MainModule?.FileName ?? string.Empty),
                    Path.GetFullPath(expectedPath),
                    StringComparison.OrdinalIgnoreCase))
                {
                    processIds.Add(process.Id);
                }
            }
            catch
            {
                // The process may exit between enumeration and inspection.
            }
            finally
            {
                process.Dispose();
            }
        }

        return processIds;
    }

    private static void StopProcessById(int processId, string expectedPath)
    {
        try
        {
            using var process = Process.GetProcessById(processId);
            if (!string.Equals(
                Path.GetFullPath(process.MainModule?.FileName ?? string.Empty),
                Path.GetFullPath(expectedPath),
                StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            process.Kill(entireProcessTree: true);
            process.WaitForExit(5000);
        }
        catch
        {
            // A stale PID or an already exited process must not block uninstall.
        }
    }
}
