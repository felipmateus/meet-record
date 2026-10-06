"""CallDetector for Windows: is Teams holding the microphone open?

Windows records, per app, when it last started and stopped using the microphone (the data
behind the privacy indicator in the taskbar), under
HKCU\\...\\CapabilityAccessManager\\ConsentStore\\microphone. While an app has the microphone
open its LastUsedTimeStop is 0. Teams opens it for the whole call, muted or not, and releases
it on hang-up, so this is the Windows counterpart of the pmset assertion heuristic (risk R3).

New Teams is a packaged app (key `MSTeams_8wekyb3d8bbwe`); a non-packaged build appears
under `NonPackaged` as its exe path with `#` for `\\`. Both are matched.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from teams_recorder.application.ports import CallState
from teams_recorder.constants import Windows


@dataclass(frozen=True)
class MicUsage:
    app: str      # registry key name: package family name or '#'-joined exe path
    start: int    # FILETIME of the last start, 0 if never
    stop: int     # FILETIME of the last stop, 0 while in use

    @property
    def in_use(self) -> bool:
        return self.start > 0 and self.stop == 0


def is_teams(app: str, process_name: str) -> bool:
    if app.startswith(Windows.TEAMS_PACKAGE_PREFIX):
        return True
    return app.rsplit(Windows.PATH_SEPARATOR, 1)[-1].lower() == process_name.lower()


def teams_in_call(usages: list[MicUsage], process_name: str) -> bool:
    return any(u.in_use for u in usages if is_teams(u.app, process_name))


def _default_find_pid(name: str) -> int | None:
    from teams_recorder.adapters.outbound.winproc import find_root_pid
    return find_root_pid(name)


@dataclass
class MicUsageCallDetector:
    process_name: str = Windows.TEAMS_PROCESS
    read_usage: Callable[[], list[MicUsage]] | None = None      # None: the registry
    find_pid: Callable[[str], int | None] = _default_find_pid

    def poll(self) -> CallState:
        try:
            usages = (self.read_usage or read_mic_usage)()
        except OSError:
            return CallState.UNKNOWN
        return CallState.IN_CALL if teams_in_call(usages, self.process_name) else CallState.IDLE

    def teams_pid(self) -> int | None:
        """The root ms-teams.exe: process loopback on it includes the helpers that play the audio."""
        try:
            return self.find_pid(self.process_name)
        except OSError:
            return None


if sys.platform == "win32":
    import winreg

    def _usage(key: winreg.HKEYType, name: str) -> MicUsage | None:
        try:
            start, _ = winreg.QueryValueEx(key, Windows.LAST_USED_START)
            stop, _ = winreg.QueryValueEx(key, Windows.LAST_USED_STOP)
        except OSError:
            return None
        return MicUsage(name, int(start), int(stop))

    def _subkeys(key: winreg.HKEYType) -> list[str]:
        names: list[str] = []
        index = 0
        while True:
            try:
                names.append(winreg.EnumKey(key, index))
            except OSError:
                return names
            index += 1

    def read_mic_usage() -> list[MicUsage]:
        usages: list[MicUsage] = []
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, Windows.MIC_CONSENT_KEY) as root:
            for name in _subkeys(root):
                with winreg.OpenKey(root, name) as app_key:
                    if name == Windows.NON_PACKAGED:
                        for exe in _subkeys(app_key):
                            with winreg.OpenKey(app_key, exe) as exe_key:
                                usage = _usage(exe_key, exe)
                                if usage:
                                    usages.append(usage)
                    else:
                        usage = _usage(app_key, name)
                        if usage:
                            usages.append(usage)
        return usages

else:
    def read_mic_usage() -> list[MicUsage]:
        raise OSError(sys.platform)
