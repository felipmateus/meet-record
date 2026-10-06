"""Windows process utilities (ctypes, no extra dependency): process table, liveness, kill.

`os.kill(pid, 0)` cannot be used on Windows to test a process: signal 0 is CTRL_C_EVENT
there. Everything Win32 sits under a `sys.platform` check so the module imports (and its
pure functions can be tested) on macOS.
"""
from __future__ import annotations

import os
import signal
import sys

from teams_recorder.constants import Windows

ProcessTable = dict[int, tuple[int, str]]   # pid -> (parent pid, executable name)


def root_pids(table: ProcessTable, exe_name: str) -> list[int]:
    """PIDs running `exe_name` whose parent is not `exe_name` too: the roots of its process trees."""
    name = exe_name.lower()
    matches = {pid for pid, (_, exe) in table.items() if exe.lower() == name}
    return sorted(pid for pid in matches if table[pid][0] not in matches)


def find_root_pid(exe_name: str) -> int | None:
    roots = root_pids(process_table(), exe_name)
    return roots[0] if roots else None


def kill(pid: int) -> None:
    """TerminateProcess (what os.kill does on Windows for any signal but the console ones)."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _ProcessEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.OpenProcess.restype = wintypes.HANDLE

    def process_table() -> ProcessTable:
        table: ProcessTable = {}
        snap = _kernel32.CreateToolhelp32Snapshot(Windows.TH32CS_SNAPPROCESS, 0)
        if not snap or snap == wintypes.HANDLE(-1).value:
            return table
        try:
            entry = _ProcessEntry32()
            entry.dwSize = ctypes.sizeof(_ProcessEntry32)
            ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                table[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), entry.szExeFile)
                ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snap)
        return table

    def is_running(pid: int) -> bool:
        handle = _kernel32.OpenProcess(Windows.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == Windows.STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)

else:
    def process_table() -> ProcessTable:
        raise OSError(sys.platform)

    def is_running(pid: int) -> bool:
        raise OSError(sys.platform)
