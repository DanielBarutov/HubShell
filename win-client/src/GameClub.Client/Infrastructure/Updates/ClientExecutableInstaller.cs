using System.Security.Cryptography;

namespace GameClub.Client.Infrastructure.Updates;

/// <summary>Only executable files are replaced; GUI shutdown and launch belong to the host.</summary>
public sealed class ClientExecutableInstaller
{
    private readonly string _directory;
    private readonly ClientUpdateStateStore _state;
    public string ExecutablePath => Path.Combine(_directory, "HubShell.exe");
    public string BackupPath => Path.Combine(_directory, ".HubShell.exe.previous");

    public ClientExecutableInstaller(string directory, ClientUpdateStateStore state)
    {
        _directory = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
        _state = state;
    }

    public static string Hash(string path)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Executable cannot be a link");
        using var source = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(source)).ToLowerInvariant();
    }

    public ClientUpdateJournal Install(string stagedExecutable, ClientReleaseManifest manifest,
        ClientUpdateJournal journal)
    {
        var staged = Path.GetFullPath(stagedExecutable);
        if (!journal.Blocked || journal.ReleaseId != manifest.ReleaseId
            || journal.ExecutableSha256 != manifest.ExecutableSha256
            || !staged.StartsWith(_directory + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            || Path.GetFileName(staged) != "HubShell.exe.new"
            || new FileInfo(staged).Length != manifest.ExecutableBytes
            || Hash(staged) != manifest.ExecutableSha256)
            throw new InvalidDataException("Invalid staged executable or deployment journal");
        var oldHash = Hash(ExecutablePath);
        if (File.Exists(BackupPath) && (File.GetAttributes(BackupPath) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Executable backup cannot be a link");
        journal = journal with { OldExecutableSha256 = oldHash, Stage = "backup_pending" };
        _state.Write(journal);
        CopyDurably(ExecutablePath, BackupPath);
        if (Hash(BackupPath) != oldHash) throw new InvalidDataException("Executable backup failed verification");
        journal = journal with { Stage = "replace_pending" };
        _state.Write(journal);
        File.Move(staged, ExecutablePath, overwrite: true);
        if (Hash(ExecutablePath) != manifest.ExecutableSha256)
            throw new InvalidDataException("Replaced executable failed verification");
        journal = journal with { Stage = "verifying" };
        _state.Write(journal);
        return journal;
    }

    public ClientUpdateJournal Rollback(ClientUpdateJournal journal)
    {
        if (journal.OldExecutableSha256 is null || !File.Exists(BackupPath)
            || Hash(BackupPath) != journal.OldExecutableSha256)
            throw new InvalidDataException("No verified previous executable is available");
        var restore = Path.Combine(_directory, ".HubShell.exe.restore");
        if (File.Exists(restore) && (File.GetAttributes(restore) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Restore staging cannot be a link");
        CopyDurably(BackupPath, restore);
        if (Hash(restore) != journal.OldExecutableSha256)
            throw new InvalidDataException("Restore staging hash does not match backup");
        File.Move(restore, ExecutablePath, overwrite: true);
        journal = journal with { Stage = "rolled_back", Blocked = true };
        _state.Write(journal);
        return journal;
    }

    public ClientUpdateJournal RecoverInterruptedReplacement(ClientUpdateJournal journal)
    {
        if (journal.Stage is not ("backup_pending" or "replace_pending" or "verifying" or "closing" or "installed"))
            return journal;
        if (File.Exists(ExecutablePath))
        {
            var installed = Hash(ExecutablePath);
            if (installed == journal.ExecutableSha256)
            {
                journal = journal with { Stage = "verifying", Blocked = true };
                _state.Write(journal);
                return journal;
            }
            if (journal.OldExecutableSha256 is not null && installed == journal.OldExecutableSha256)
            {
                journal = journal with { Stage = "rolled_back", Blocked = true };
                _state.Write(journal);
                return journal;
            }
        }
        return Rollback(journal);
    }

    private static void CopyDurably(string source, string destination)
    {
        File.Copy(source, destination, overwrite: true);
        using var file = new FileStream(destination, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        file.Flush(flushToDisk: true);
    }
}
