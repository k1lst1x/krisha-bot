using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

internal static class KrishaBotLauncher
{
    private static int Main(string[] args)
    {
        string exePath = Assembly.GetExecutingAssembly().Location;
        string exeDir = Path.GetDirectoryName(exePath);
        string exeName = Path.GetFileNameWithoutExtension(exePath);
        string batName = PickBatchFile(exeName);
        string batPath = Path.Combine(exeDir, batName);

        Console.Title = "Krisha Bot Launcher";
        Console.WriteLine("Krisha Bot Launcher");
        Console.WriteLine("Running: " + batName);
        Console.WriteLine();

        if (!File.Exists(batPath))
        {
            Console.WriteLine("[ERROR] File was not found: " + batPath);
            Pause();
            return 2;
        }

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = GetCmdPath();
            psi.Arguments = "/d /s /c \"" + QuoteForCmd(batPath) + BuildArgs(args) + "\"";
            psi.WorkingDirectory = exeDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = false;

            Process process = Process.Start(psi);
            process.WaitForExit();

            int exitCode = process.ExitCode;
            Console.WriteLine();
            Console.WriteLine("Finished with exit code: " + exitCode);
            Pause();
            return exitCode;
        }
        catch (Exception ex)
        {
            Console.WriteLine("[ERROR] Could not start " + batName);
            Console.WriteLine(ex.Message);
            Pause();
            return 1;
        }
    }

    private static string PickBatchFile(string exeName)
    {
        string upperName = (exeName ?? String.Empty).ToUpperInvariant();
        if (upperName.IndexOf("RUN") >= 0 || upperName.IndexOf("2_") >= 0)
        {
            return "2_RUN_BOT.bat";
        }

        return "1_INSTALL_ONCE.bat";
    }

    private static string GetCmdPath()
    {
        string cmd = Environment.GetEnvironmentVariable("ComSpec");
        return String.IsNullOrEmpty(cmd) ? "cmd.exe" : cmd;
    }

    private static string BuildArgs(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return String.Empty;
        }

        string result = String.Empty;
        for (int i = 0; i < args.Length; i++)
        {
            result += " " + QuoteForCmd(args[i]);
        }

        return result;
    }

    private static string QuoteForCmd(string value)
    {
        if (value == null)
        {
            value = String.Empty;
        }

        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    private static void Pause()
    {
        Console.WriteLine();
        Console.WriteLine("Press Enter to close this window.");
        try
        {
            Console.ReadLine();
        }
        catch
        {
        }
    }
}
