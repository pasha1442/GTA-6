"""Best-effort Windows toast notification. Failures are ignored."""
from __future__ import annotations

import os
import subprocess
import sys

_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$txt = $tpl.GetElementsByTagName('text')
$txt.Item(0).AppendChild($tpl.CreateTextNode($env:CLIPPER_TITLE)) > $null
$txt.Item(1).AppendChild($tpl.CreateTextNode($env:CLIPPER_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($tpl))
"""


def notify(title: str, body: str) -> None:
    if sys.platform != "win32":
        return
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
            env={**os.environ, "CLIPPER_TITLE": title, "CLIPPER_BODY": body},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        pass
