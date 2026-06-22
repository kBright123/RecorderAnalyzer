import subprocess
import threading
import platform
import os


def _run_dialog(cmd, callback):
    def _run():
        path = None
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                path = result.stdout.strip()
        except Exception:
            path = None
        if callback:
            callback(path)
    threading.Thread(target=_run, daemon=True).start()


def pick_file(title="选择文件", callback=None):
    system = platform.system()
    if system == "Linux":
        _run_dialog(["zenity", "--file-selection", "--title", title], callback)
    elif system == "Windows":
        import tempfile
        ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Title = "{title}"
if ($f.ShowDialog() -eq "OK") {{ $f.FileName }}
'''
        _run_dialog(["powershell", "-NoProfile", "-Command", ps_script], callback)
    elif system == "Darwin":
        _run_dialog([
            "osascript", "-e",
            f'POSIX path of (choose file with prompt "{title}")',
        ], callback)
    else:
        if callback:
            callback(None)


def save_file(title="保存文件", filename="", callback=None):
    system = platform.system()
    if system == "Linux":
        cmd = ["zenity", "--file-selection", "--save", "--title", title]
        if filename:
            cmd.extend(["--filename", filename])
        _run_dialog(cmd, callback)
    elif system == "Windows":
        import tempfile
        ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.SaveFileDialog
$f.Title = "{title}"
$f.FileName = "{filename}"
if ($f.ShowDialog() -eq "OK") {{ $f.FileName }}
'''
        _run_dialog(["powershell", "-NoProfile", "-Command", ps_script], callback)
    elif system == "Darwin":
        _run_dialog([
            "osascript", "-e",
            f'set f to choose file name with prompt "{title}" default name "{filename}"',
            "-e", "POSIX path of f",
        ], callback)
    else:
        if callback:
            callback(None)
