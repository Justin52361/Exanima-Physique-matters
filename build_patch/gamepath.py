"""Finds Exanima.exe (Steam install, any library folder)."""
import os
import re

def _steam_roots():
    roots = []
    try:
        import winreg
        for hive, sub, val in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                               (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                               (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    roots.append(winreg.QueryValueEx(k, val)[0])
            except OSError:
                pass
    except ImportError:
        pass
    for env in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(env):
            roots.append(os.path.join(os.environ[env], 'Steam'))
    return roots

def find_exe():
    seen, libs = set(), []
    for root in _steam_roots():
        root = os.path.normpath(root)
        if root in seen: continue
        seen.add(root); libs.append(root)
        vdf = os.path.join(root, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf):
            try:
                text = open(vdf, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                lib = os.path.normpath(m.group(1).replace('\\\\', '\\'))
                if lib not in seen: seen.add(lib); libs.append(lib)
    for lib in libs:
        exe = os.path.join(lib, 'steamapps', 'common', 'Exanima', 'Exanima.exe')
        if os.path.exists(exe):
            return exe
    return None
