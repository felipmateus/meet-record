// Win32 / COM interop that NAudio does not expose: process-loopback activation
// (ActivateAudioInterfaceAsync with AUDIOCLIENT_ACTIVATION_PARAMS) and the process tree
// (Toolhelp32) used by --list to report each audio session's parent process.
using System.Runtime.InteropServices;
using NAudio.CoreAudioApi.Interfaces;

namespace TeamsTap;

[ComImport, Guid("41D949AB-9862-444A-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IActivateAudioInterfaceCompletionHandler
{
    void ActivateCompleted(IActivateAudioInterfaceAsyncOperation activateOperation);
}

[ComImport, Guid("72A22D78-CDE4-431D-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IActivateAudioInterfaceAsyncOperation
{
    void GetActivateResult(out int activateResult, [MarshalAs(UnmanagedType.IUnknown)] out object activatedInterface);
}

/// Marker interface: the completion handler is called on an arbitrary MTA thread.
[ComImport, Guid("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IAgileObject { }

[ClassInterface(ClassInterfaceType.None)]
internal sealed class ActivationHandler : IActivateAudioInterfaceCompletionHandler, IAgileObject
{
    private readonly TaskCompletionSource<IAudioClient> _tcs = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public Task<IAudioClient> Task => _tcs.Task;

    public void ActivateCompleted(IActivateAudioInterfaceAsyncOperation activateOperation)
    {
        try
        {
            activateOperation.GetActivateResult(out int hr, out object iface);
            if (hr != 0) { _tcs.TrySetException(Marshal.GetExceptionForHR(hr) ?? new COMException("activation failed", hr)); return; }
            _tcs.TrySetResult((IAudioClient)iface);
        }
        catch (Exception ex) { _tcs.TrySetException(ex); }
    }
}

internal static class Native
{
    public const string VirtualProcessLoopback = "VAD\\Process_Loopback";
    public static readonly Guid IID_IAudioClient = new("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2");
    private const ushort VT_BLOB = 65;
    private const int AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1;
    private const int PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0;
    private const int PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE = 1;

    [DllImport("Mmdevapi.dll", ExactSpelling = true, PreserveSig = false)]
    private static extern void ActivateAudioInterfaceAsync(
        [MarshalAs(UnmanagedType.LPWStr)] string deviceInterfacePath,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
        IntPtr activationParams,
        IActivateAudioInterfaceCompletionHandler completionHandler,
        out IActivateAudioInterfaceAsyncOperation activationOperation);

    [StructLayout(LayoutKind.Sequential)]
    private struct AudioClientActivationParams
    {
        public int ActivationType;
        public uint TargetProcessId;
        public int ProcessLoopbackMode;
    }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    private struct PropVariantBlob
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public uint cbSize;
        [FieldOffset(16)] public IntPtr pBlobData;
    }

    /// Activates an IAudioClient that captures what `pid` (and, by default, its child processes) plays.
    public static async Task<IAudioClient> ActivateProcessLoopbackAsync(uint pid, bool includeTree)
    {
        var p = new AudioClientActivationParams
        {
            ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
            TargetProcessId = pid,
            ProcessLoopbackMode = includeTree ? PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE : PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE,
        };
        IntPtr paramsPtr = Marshal.AllocHGlobal(Marshal.SizeOf<AudioClientActivationParams>());
        IntPtr variantPtr = Marshal.AllocHGlobal(Marshal.SizeOf<PropVariantBlob>());
        try
        {
            Marshal.StructureToPtr(p, paramsPtr, false);
            Marshal.StructureToPtr(new PropVariantBlob { vt = VT_BLOB, cbSize = (uint)Marshal.SizeOf<AudioClientActivationParams>(), pBlobData = paramsPtr }, variantPtr, false);
            var handler = new ActivationHandler();
            ActivateAudioInterfaceAsync(VirtualProcessLoopback, IID_IAudioClient, variantPtr, handler, out _);
            return await handler.Task.ConfigureAwait(false);
        }
        finally
        {
            Marshal.FreeHGlobal(variantPtr);
            Marshal.FreeHGlobal(paramsPtr);
        }
    }

    // --- process tree (Toolhelp32) ---------------------------------------------------
    private const uint TH32CS_SNAPPROCESS = 0x00000002;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct ProcessEntry32
    {
        public uint dwSize; public uint cntUsage; public uint th32ProcessID; public IntPtr th32DefaultHeapID;
        public uint th32ModuleID; public uint cntThreads; public uint th32ParentProcessID; public int pcPriClassBase;
        public uint dwFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern bool Process32FirstW(IntPtr snap, ref ProcessEntry32 e);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern bool Process32NextW(IntPtr snap, ref ProcessEntry32 e);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr h);

    /// pid → (parent pid, executable name) for every running process.
    public static Dictionary<uint, (uint Parent, string Exe)> ProcessTable()
    {
        var table = new Dictionary<uint, (uint, string)>();
        IntPtr snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snap == IntPtr.Zero || snap == new IntPtr(-1)) return table;
        try
        {
            var e = new ProcessEntry32 { dwSize = (uint)Marshal.SizeOf<ProcessEntry32>() };
            for (bool ok = Process32FirstW(snap, ref e); ok; ok = Process32NextW(snap, ref e))
                table[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile);
        }
        finally { CloseHandle(snap); }
        return table;
    }
}
