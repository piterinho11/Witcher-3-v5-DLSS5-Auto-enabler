import os
import sys
import re
import time
import shutil
import traceback
import ctypes
from ctypes import wintypes
import winreg
import atexit
import signal
import json

# =====================================================================
#  SYSTEM CONFIGURATION & METADATA (v6.0)
# =====================================================================
SCRIPT_NAME = "DLSS 5 - 3 Wiedźmin 3, Najlepszy"
VERSION = "6.0.0"
CONFIG_FILE_NAME = "dlss5_config.json"
INGAME_NOTIFICATION = "Auto DLSS5 ON"

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)

def set_console_title():
    try:
        kernel32.SetConsoleTitleW(SCRIPT_NAME)
    except Exception:
        pass

def disable_quickedit():
    """Disables QuickEdit Mode in the Windows console to prevent accidental thread freezing."""
    try:
        STD_INPUT_HANDLE = -10
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_INSERT_MODE = 0x0020
        ENABLE_EXTENDED_FLAGS = 0x0080
        h_stdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
            new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE & ~ENABLE_INSERT_MODE) | ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(h_stdin, new_mode)
    except Exception:
        pass

def ensure_admin():
    """
    Ensures execution with elevated administrator privileges.
    Fully compatible with standard .py execution and compiled PyInstaller .exe binaries.
    """
    try:
        is_admin = (shell32.IsUserAnAdmin() != 0)
    except Exception:
        is_admin = False

    if is_admin:
        print("[OK] Administrator privileges: ACTIVE")
        return

    print("[*] Administrator privileges required. Relaunching with elevated rights...")
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        exe = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        work_dir = os.path.dirname(exe)
    else:
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}" ' + " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        work_dir = os.path.dirname(script)

    ret = shell32.ShellExecuteW(None, "runas", exe, params.strip(), work_dir, 1)
    if ret > 32:
        os._exit(0)
    else:
        print("[!] Could not automatically elevate privileges - continuing in current console.")

# =====================================================================
#  WIN32 API CONSTANTS & DEFINITIONS
# =====================================================================
PROCESS_QUERY_INFORMATION = 0x0400
SYNCHRONIZE = 0x00100000

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WAIT_TIMEOUT = 0x00000102

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_ulonglong),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * wintypes.MAX_PATH),
    ]

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL

kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

# =====================================================================
#  PERSISTENT CONFIGURATION (JSON STORAGE)
# =====================================================================
def get_app_directory():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def get_config_path():
    return os.path.join(get_app_directory(), CONFIG_FILE_NAME)

def load_stored_config():
    cfg_path = get_config_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_stored_config(cfg_dict):
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Failed to save configuration file {CONFIG_FILE_NAME}: {e}")

# =====================================================================
#  DYNAMIC DXGI.DLL MICRO-PATCHER (NOTIFICATION BANNER MUTING)
# =====================================================================
class OptiScalerPatcher:
    """
    Manages the dxgi.dll micro-patch that mutes the DLSS-NR notification banner during the session.
    The patch is applied at launch and restored automatically upon exit.
    """
    DXGI_RAW_OFFSET = 0x1D645A

    ORIG_BYTES = bytes([
        0x48, 0x8B, 0x15, 0x5F, 0xE6, 0x68, 0x01, 0x4C, 0x8D, 0x85, 0xF0, 0x00, 0x00, 0x00,
        0x48, 0x3B, 0x15, 0x59, 0xE6, 0x68, 0x01, 0x74, 0x12, 0xE8, 0x0A, 0x80, 0xE7, 0xFF,
        0x48, 0x81, 0x05, 0x3F, 0xE6, 0x68, 0x01, 0x60, 0x30, 0x00, 0x00, 0xEB, 0x06, 0xE8,
        0x98, 0x79, 0xE7, 0xFF, 0x90
    ])
    PATCH_BYTES = bytes([0xEB, 0x2D]) + (b'\x90' * 45)

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.dll_path = os.path.join(game_dir, "bin", "x64_dx12", "dxgi.dll")
        if not os.path.exists(self.dll_path):
            alt_path = os.path.join(game_dir, "dxgi.dll")
            if os.path.exists(alt_path):
                self.dll_path = alt_path
        self.bak_path = self.dll_path + ".bak"
        self.patched_disk = False

    def is_optiscaler_present(self) -> bool:
        return os.path.exists(self.dll_path)

    def apply_disk_patch(self) -> bool:
        if not os.path.exists(self.dll_path):
            return False

        try:
            if not os.path.exists(self.bak_path):
                shutil.copy2(self.dll_path, self.bak_path)

            with open(self.dll_path, "rb") as f:
                data = bytearray(f.read())

            offset = self.DXGI_RAW_OFFSET
            if offset + 47 <= len(data) and data[offset : offset + 47] == self.ORIG_BYTES:
                data[offset : offset + 47] = self.PATCH_BYTES
                with open(self.dll_path, "wb") as f:
                    f.write(data)
                self.patched_disk = True
                print("[OK] Micro-patch applied to dxgi.dll (DLSS-NR notification banner muted).")
                return True
            elif offset + 47 <= len(data) and data[offset : offset + 47] == self.PATCH_BYTES:
                print("[*] dxgi.dll already has active micro-patch (banner muted).")
                self.patched_disk = True
                return True
            else:
                pos = data.find(self.ORIG_BYTES)
                if pos != -1:
                    data[pos : pos + 47] = self.PATCH_BYTES
                    with open(self.dll_path, "wb") as f:
                        f.write(data)
                    self.patched_disk = True
                    print(f"[OK] Micro-patch applied to dxgi.dll at offset {hex(pos)}.")
                    return True
                elif data.find(self.PATCH_BYTES) != -1:
                    print("[*] dxgi.dll already has active micro-patch.")
                    self.patched_disk = True
                    return True
                else:
                    print("[INFO] Your dxgi.dll build has a different binary signature - notification banner patch skipped (game functions normally).")
                    return False
        except PermissionError:
            print("[*] dxgi.dll is locked by another process.")
            return False
        except Exception as e:
            print(f"[!] Error applying patch to dxgi.dll: {e}")
            return False

    def restore_disk_patch(self):
        if not self.patched_disk or not os.path.exists(self.dll_path):
            return
        try:
            with open(self.dll_path, "rb") as f:
                data = bytearray(f.read())

            offset = self.DXGI_RAW_OFFSET
            if offset + 47 <= len(data) and data[offset : offset + 47] == self.PATCH_BYTES:
                data[offset : offset + 47] = self.ORIG_BYTES
                with open(self.dll_path, "wb") as f:
                    f.write(data)
                self.patched_disk = False
                print("[*] Restored original dxgi.dll.")
            else:
                pos = data.find(self.PATCH_BYTES)
                if pos != -1:
                    data[pos : pos + 47] = self.ORIG_BYTES
                    with open(self.dll_path, "wb") as f:
                        f.write(data)
                    self.patched_disk = False
                    print(f"[*] Restored original dxgi.dll at offset {hex(pos)}.")
        except PermissionError:
            pass
        except Exception as e:
            print(f"[!] Could not restore dxgi.dll: {e}")

# =====================================================================
#  OPTISCALER.INI CLEANER
# =====================================================================
def cleanup_optiscaler_ini(game_dir):
    ini_paths = [
        os.path.join(game_dir, "bin", "x64_dx12", "OptiScaler.ini"),
        os.path.join(game_dir, "bin", "x64", "OptiScaler.ini"),
        os.path.join(game_dir, "OptiScaler.ini"),
    ]
    junk_keys = {
        "nonotifications", "showclock", "osdduration", "messageduration",
        "showtoast", "showstatus", "showindicator", "enableosd",
        "notificationduration", "showosd", "notifications",
        "shownotifications", "showmessages"
    }

    for path in ini_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                new_lines = []
                cleaned = False
                in_menu_section = False

                for line in lines:
                    line_clean = line.strip()
                    if line_clean.startswith("[") and line_clean.endswith("]"):
                        in_menu_section = (line_clean.lower() == "[menu]")
                        new_lines.append(line)
                        continue

                    if in_menu_section and "=" in line_clean and not line_clean.startswith(";"):
                        key = line_clean.split("=", 1)[0].strip().lower()
                        if key in junk_keys:
                            cleaned = True
                            continue

                    new_lines.append(line)

                if cleaned:
                    with open(path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    print(f"[OK] Cleaned {os.path.basename(path)} of unsupported notification parameters.")
            except Exception:
                pass

# =====================================================================
#  SECTION-AWARE OPTISCALER.INI PARSER & WIN32 BRIDGE
# =====================================================================
def parse_vk_value(val_str: str) -> int:
    val_clean = val_str.split(";")[0].strip()
    if val_clean.startswith("0x") or val_clean.startswith("0X"):
        try:
            return int(val_clean, 16)
        except ValueError:
            pass
    elif val_clean.isdigit():
        try:
            return int(val_clean)
        except ValueError:
            pass
    elif len(val_clean) == 1:
        return ord(val_clean.upper())

    vk_map = {
        "numpad/": 0x6F, "divide": 0x6F, "num/": 0x6F,
        "numpad*": 0x6A, "multiply": 0x6A,
        "numpad-": 0x6D, "subtract": 0x6D,
        "numpad+": 0x6B, "add": 0x6B,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
        "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
        "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    }
    return vk_map.get(val_clean.lower(), None)

def get_optiscaler_config(game_dir):
    """
    Parses OptiScaler.ini with section awareness.
    Guarantees that [Menu] ShortcutKey never overrides the DLSS/Upscaler toggle key.
    """
    ini_paths = [
        os.path.join(game_dir, "bin", "x64_dx12", "OptiScaler.ini"),
        os.path.join(game_dir, "bin", "x64", "OptiScaler.ini"),
        os.path.join(game_dir, "OptiScaler.ini"),
    ]
    vk_code = 0x6F  # VK_DIVIDE (Numpad /) default
    initial_enabled = False
    found_key = False

    for path in ini_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    current_section = ""
                    for line in f:
                        line_clean = line.strip()
                        if line_clean.startswith("[") and line_clean.endswith("]"):
                            current_section = line_clean[1:-1].strip().lower()
                            continue

                        if "=" in line_clean and not line_clean.startswith(";"):
                            key, val = [x.strip() for x in line_clean.split("=", 1)]
                            key_lower = key.lower()
                            val_clean = val.split(";")[0].strip()

                            if current_section in ("dlssnr", "upscaler", "fsr", "xess", "dlss", "framegen"):
                                if any(k in key_lower for k in ("togglekey", "hotkey", "toggle", "shortcut")):
                                    parsed = parse_vk_value(val_clean)
                                    if parsed is not None:
                                        vk_code = parsed
                                        found_key = True

                            elif current_section not in ("menu", "overlay", "imgui"):
                                if not found_key and any(k in key_lower for k in ("togglekey", "hotkey", "toggle")):
                                    parsed = parse_vk_value(val_clean)
                                    if parsed is not None:
                                        vk_code = parsed
                                        found_key = True

                            if key_lower in ("enabled", "upscalerenabled"):
                                initial_enabled = val_clean.lower() in ("true", "1", "on")
            except Exception:
                pass
    return vk_code, initial_enabled

class OptiScalerDirectBridge:
    def __init__(self, game_dir, override_vk=None):
        self.cached_hwnds = []
        self.last_pid = None
        auto_vk, self.initial_state = get_optiscaler_config(game_dir)
        self.vk_code = override_vk if override_vk else auto_vk
        self._scancode = user32.MapVirtualKeyW(self.vk_code, 0)
        self._lparam_down = 0x00000001 | (self._scancode << 16)
        self._lparam_up = self._lparam_down | (1 << 30) | (1 << 31)
        self.last_simulated_time = 0.0
        print(f"[*] Configured OptiScaler hotkey (VK): {hex(self.vk_code)} (Scancode: {hex(self._scancode)})")

    def get_game_hwnds(self, pid: int):
        if not pid:
            return []
        if pid == self.last_pid and self.cached_hwnds:
            valid = [h for h in self.cached_hwnds if user32.IsWindow(h)]
            if valid:
                self.cached_hwnds = valid
                return valid

        hwnds = []
        def _enum_cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                win_pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
                if win_pid.value == pid:
                    hwnds.append(hwnd)
            return True

        cb_func = WNDENUMPROC(_enum_cb)
        user32.EnumWindows(cb_func, 0)
        self.last_pid = pid
        self.cached_hwnds = hwnds
        return hwnds

    def is_game_foreground(self, pid: int) -> bool:
        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd:
            return False
        hwnds = self.get_game_hwnds(pid)
        return fg_hwnd in hwnds

    def toggle_optiscaler(self, pid: int) -> str:
        if not pid:
            return "No process"
        hwnds = self.get_game_hwnds(pid)
        if not hwnds:
            return "No HWND window"

        self.last_simulated_time = time.time()
        for hwnd in hwnds:
            user32.PostMessageW(hwnd, WM_KEYDOWN, self.vk_code, self._lparam_down)
        time.sleep(0.02)
        for hwnd in hwnds:
            user32.PostMessageW(hwnd, WM_KEYUP, self.vk_code, self._lparam_up)
        return f"PostMessage VK {hex(self.vk_code)}"

class PlayerHotkeyTracker:
    def __init__(self, vk_code: int):
        self.vk_code = vk_code
        self.was_pressed = False

    def check_player_toggle(self, is_foreground: bool, last_simulated_time: float) -> bool:
        if not is_foreground:
            self.was_pressed = False
            return False

        if (time.time() - last_simulated_time) < 0.20:
            return False

        state = user32.GetAsyncKeyState(self.vk_code)
        is_pressed = bool(state & 0x8000)

        toggled = False
        if is_pressed and not self.was_pressed:
            toggled = True
        self.was_pressed = is_pressed
        return toggled

def get_witcher_pid():
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or not snap:
        return None
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                if pe.szExeFile.lower() == "witcher3.exe":
                    return pe.th32ProcessID
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return None

# =====================================================================
#  GAME & CONFIG DIRECTORY DETECTION (STEAM / GOG / EPIC)
# =====================================================================
def get_user_config_folders(stored_path=None):
    folders = []
    if stored_path and os.path.exists(stored_path):
        folders.append(stored_path)

    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    shell32.SHGetFolderPathW(None, 5, None, 0, buf)

    candidates = [
        os.path.join(buf.value, "The Witcher 3"),
        os.path.expanduser(r"~\Documents\The Witcher 3"),
    ]

    onedrive_vars = [os.environ.get("OneDrive"), os.environ.get("OneDriveConsumer"), os.environ.get("OneDriveCommercial")]
    for od in onedrive_vars:
        if od and os.path.exists(od):
            for sub in ("Documents", "Dokumenty", "Dokumente", "Documentos", "Documenti"):
                cand = os.path.join(od, sub, "The Witcher 3")
                candidates.append(cand)

    for folder in candidates:
        if os.path.exists(folder) and folder not in folders:
            folders.append(folder)

    return folders

def prompt_folder_gui(title: str, check_file: str = None) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title=title)
        root.destroy()
        if folder and os.path.exists(folder):
            if check_file:
                if os.path.exists(os.path.join(folder, check_file)):
                    return folder
            else:
                return folder
    except Exception:
        pass
    return None

def resolve_user_config_folder(stored_cfg: dict) -> str:
    folders = get_user_config_folders(stored_cfg.get("user_config_dir"))
    for f in folders:
        if os.path.exists(os.path.join(f, "user.settings")) or os.path.exists(os.path.join(f, "dx12user.settings")):
            return f

    print("\n[!] The Witcher 3 Documents folder could not be found automatically.")
    print("    Please select the 'The Witcher 3' directory in your Documents...")
    chosen = prompt_folder_gui("Select 'The Witcher 3' directory in Documents (with user.settings)")
    if chosen:
        stored_cfg["user_config_dir"] = chosen
        save_stored_config(stored_cfg)
        return chosen
    return None

def find_steam_libraries():
    lib_paths = []
    steam_path = None
    for root_h, subk in [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ]:
        try:
            with winreg.OpenKey(root_h, subk) as k:
                val, _ = winreg.QueryValueEx(k, "SteamPath") if "Valve\\Steam" in subk else winreg.QueryValueEx(k, "InstallPath")
                if os.path.exists(val):
                    steam_path = val
                    break
        except OSError:
            pass

    if steam_path:
        lib_vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(lib_vdf):
            try:
                with open(lib_vdf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = re.search(r'"path"\s*"([^"]+)"', line)
                        if m:
                            p = m.group(1).replace(r"\\", "\\")
                            if os.path.exists(p) and p not in lib_paths:
                                lib_paths.append(p)
            except Exception:
                pass
    return lib_paths

def find_witcher3_folder(stored_cfg: dict):
    if "game_dir" in stored_cfg:
        gdir = stored_cfg["game_dir"]
        if os.path.exists(os.path.join(gdir, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")):
            return gdir

    reg_checks = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 292030", "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 292030", "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games\1207664643", "path"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games\1207664643", "path"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games\1495134320", "path"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games\1495134320", "path"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games\1640424747", "path"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games\1640424747", "path"),
    ]
    for root, subkey, val_name in reg_checks:
        try:
            with winreg.OpenKey(root, subkey) as k:
                path, _ = winreg.QueryValueEx(k, val_name)
                if path and os.path.exists(os.path.join(path, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")):
                    stored_cfg["game_dir"] = path
                    save_stored_config(stored_cfg)
                    return path
        except OSError:
            pass

    epic_manifests = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if os.path.exists(epic_manifests):
        try:
            for item in os.listdir(epic_manifests):
                if item.endswith(".item"):
                    item_path = os.path.join(epic_manifests, item)
                    with open(item_path, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                        if "Witcher" in data.get("DisplayName", ""):
                            inst_loc = data.get("InstallLocation", "")
                            if os.path.exists(os.path.join(inst_loc, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")):
                                stored_cfg["game_dir"] = inst_loc
                                save_stored_config(stored_cfg)
                                return inst_loc
        except Exception:
            pass

    common_subdirs = [
        "The Witcher 3", "The Witcher 3 Wild Hunt", "The Witcher 3 Wild Hunt GOTY"
    ]
    candidate_bases = [
        r"C:\Program Files (x86)\Steam\steamapps\common",
        r"C:\Program Files\Steam\steamapps\common",
        r"C:\Program Files (x86)\GOG Galaxy\Games",
        r"C:\Games", r"D:\Games", r"E:\Games", r"F:\Games",
        r"C:\Gry", r"D:\Gry", r"E:\Gry", r"F:\Gry",
    ]
    for lib in find_steam_libraries():
        candidate_bases.append(os.path.join(lib, "steamapps", "common"))

    for base in candidate_bases:
        for sub in common_subdirs:
            full_p = os.path.join(base, sub)
            if os.path.exists(os.path.join(full_p, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")):
                stored_cfg["game_dir"] = full_p
                save_stored_config(stored_cfg)
                return full_p

    print("\n[*] Game directory not found automatically. Please select The Witcher 3 main folder...")
    chosen = prompt_folder_gui(
        "Select The Witcher 3 main game folder",
        os.path.join("content", "content0", "scripts", "game", "player", "playerWitcher.ws")
    )
    if chosen:
        stored_cfg["game_dir"] = chosen
        save_stored_config(stored_cfg)
        return chosen

    return None

# =====================================================================
#  SETTINGS FILES & WITCHERSCRIPT (PURE HIGH-PERFORMANCE FILE CHANNEL)
# =====================================================================
def get_settings_files(config_folder=None):
    files = []
    folders = []
    if config_folder and os.path.exists(config_folder):
        folders.append(config_folder)
    for f in get_user_config_folders():
        if f not in folders:
            folders.append(f)
    for folder in folders:
        for fname in ("dx12user.settings", "user.settings"):
            fpath = os.path.join(folder, fname)
            if fpath not in files:
                files.append(fpath)
    return files

def prepare_settings_files(settings_files, config_folder=None):
    for fpath in settings_files:
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                modified = False
                if "[AutoOpti]" not in text:
                    text = text.rstrip() + "\n\n[AutoOpti]\nCutsceneActive=0\n"
                    modified = True
                if "[Gameplay]" in text and "OptiCutscene=" not in text:
                    text = text.replace("[Gameplay]", "[Gameplay]\nOptiCutscene=0", 1)
                    modified = True
                if re.search(r'(?:OptiCutscene|CutsceneActive)\s*=\s*(?:1|true)', text, flags=re.IGNORECASE):
                    text = re.sub(
                        r'((?:OptiCutscene|CutsceneActive)\s*=\s*)(?:1|true)',
                        r'\g<1>0',
                        text,
                        flags=re.IGNORECASE
                    )
                    modified = True
                if modified:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(text)
            except OSError:
                pass

    folders = []
    if config_folder and os.path.exists(config_folder):
        folders.append(config_folder)
    for f in get_user_config_folders():
        if f not in folders:
            folders.append(f)

    for folder in folders:
        mods_ini = os.path.join(folder, "mods.settings")
        try:
            text = ""
            if os.path.exists(mods_ini):
                with open(mods_ini, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            if "[modAutoOptiCutscene]" not in text:
                text = "[modAutoOptiCutscene]\nEnabled=1\nPriority=1\n\n" + text
            else:
                text = re.sub(
                    r'(\[modAutoOptiCutscene\][^\[]*?Enabled\s*=\s*)\d+',
                    r'\g<1>1',
                    text,
                    flags=re.DOTALL
                )
            with open(mods_ini, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass

def read_ws_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        text = raw.decode("utf-16", errors="ignore")
    elif raw.startswith(b'\xef\xbb\xbf'):
        text = raw.decode("utf-8-sig", errors="ignore")
    else:
        text = raw.decode("utf-8", errors="ignore")
    return text.replace('\x00', '')

def inject_ws_code(content):
    content = content.replace('\\"', '"')

    # Remove any old or legacy injected variables
    content = re.sub(
        r'\s*private\s+var\s+opti(?:Arr|MarkerA|MarkerB|MarkerC_State|MarkerD|MarkerE_Tick|Notified)\b.*?(?=event\s+OnSpawned\s*\()',
        '\n\n\t',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'\s*optiMarkerC_State\s*=\s*0;.*?ShowNotification\([^)]+\)\s*;',
        '',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'\s*optiMarkerC_State\s*=\s*0;.*?AddTimer\(\s*\'AutoOptiCutsceneTimer\'[^\n]+\n',
        '\n',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'\s*optiArr\.Clear\(\);.*?optiMarkerE_Tick\s*=\s*0;',
        '',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'\s*optiMarkerA\s*=\s*0;.*?optiMarkerE_Tick\s*=\s*0;',
        '',
        content,
        flags=re.DOTALL
    )
    content = re.sub(r'\s*UpdateAutoOptiCutsceneState\([^)]*\);', '', content)

    injected_functions = f"""
\tprivate var optiMarkerC_State : int;
\tprivate var optiNotified : bool;

\tpublic function UpdateAutoOptiCutsceneState( optional forceCutscene : bool )
\t{{
\t\tvar isCutscene : bool;
\t\tvar newState : int;

\t\tif ( theGame.IsPaused() || theGame.GetPhotomodeEnabled() || theGame.GetGuiManager().IsAnyMenu() )
\t\t{{
\t\t\tisCutscene = false;
\t\t}}
\t\telse
\t\t{{
\t\t\tisCutscene = forceCutscene
\t\t\t          || theGame.IsDialogOrCutscenePlaying()
\t\t\t          || thePlayer.IsInCutsceneIntro()
\t\t\t          || theGame.IsCurrentlyPlayingNonGameplayScene()
\t\t\t          || theGame.IsBlackscreen()
\t\t\t          || (theInput.GetContext() == 'Scene')
\t\t\t          || (theInput.GetContext() == 'EMPTY_CONTEXT')
\t\t\t          || (!GetBIsInputAllowed() && !IsInCombat() && !IsInCombatAction());
\t\t}}

\t\tif ( !optiNotified )
\t\t{{
\t\t\tif ( !theGame.IsBlackscreen() && !theGame.IsPaused() && !isCutscene && theGame.GetGuiManager() && !theGame.GetGuiManager().IsAnyMenu() )
\t\t\t{{
\t\t\t\toptiNotified = true;
\t\t\t\ttheGame.GetGuiManager().ShowNotification( "{INGAME_NOTIFICATION}" );
\t\t\t}}
\t\t}}

\t\tif ( isCutscene )
\t\t{{
\t\t\tnewState = 222222;
\t\t}}
\t\telse
\t\t{{
\t\t\tnewState = 111111;
\t\t}}

\t\tif ( optiMarkerC_State != newState )
\t\t{{
\t\t\toptiMarkerC_State = newState;
\t\t\tif ( isCutscene )
\t\t\t{{
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Gameplay', 'OptiCutscene', "0");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Gameplay', 'OptiCutscene', "1");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Hidden', 'OptiCutscene', "0");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Hidden', 'OptiCutscene', "1");
\t\t\t}}
\t\t\telse
\t\t\t{{
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Gameplay', 'OptiCutscene', "1");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Gameplay', 'OptiCutscene', "0");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Hidden', 'OptiCutscene', "1");
\t\t\t\ttheGame.GetInGameConfigWrapper().SetVarValue('Hidden', 'OptiCutscene', "0");
\t\t\t}}
\t\t\ttheGame.SaveUserSettings();
\t\t}}
\t}}

\ttimer function AutoOptiCutsceneTimer( optional deltaTime : float , optional id : int )
\t{{
\t\tUpdateAutoOptiCutsceneState( false );
\t}}
"""

    content, c1 = re.subn(
        r'(event\s+OnSpawned\s*\(\s*spawnData\s*:\s*SEntitySpawnData\s*\))',
        lambda m: injected_functions + '\n\t' + m.group(1),
        content,
        count=1
    )

    spawn_hook = (
        '\n\t\toptiMarkerC_State = 0;'
        '\n\t\toptiNotified = false;'
        '\n\t\tUpdateAutoOptiCutsceneState( false );'
        "\n\t\tAddTimer( 'AutoOptiCutsceneTimer', 0.1f, true );"
    )
    content, c2 = re.subn(
        r'(super\.OnSpawned\s*\(\s*spawnData\s*\)\s*;)',
        lambda m: m.group(1) + spawn_hook,
        content,
        count=1
    )

    destroy_hook = (
        '\n\t\toptiMarkerC_State = 0;'
    )
    content, c3 = re.subn(
        r'(event\s+OnDestroyed\s*\(\s*\)\s*\{)',
        lambda m: m.group(1) + destroy_hook,
        content,
        count=1
    )

    content, c4 = re.subn(
        r'(timer\s+function\s+UpdateGamepadTriggerEffect\s*\([^{]+\{)',
        lambda m: m.group(1) + '\n\t\tUpdateAutoOptiCutsceneState( false );',
        content,
        count=1
    )

    content, c5 = re.subn(
        r'(super\.OnPlayerTickTimer\s*\(\s*deltaTime\s*\)\s*;)',
        lambda m: m.group(1) + '\n\t\tUpdateAutoOptiCutsceneState( false );',
        content,
        count=1
    )

    content, c6 = re.subn(
        r'(super\.OnBlockingSceneStarted\s*\(\s*scene\s*\)\s*;)',
        lambda m: m.group(1) + '\n\t\tUpdateAutoOptiCutsceneState( true );',
        content,
        count=1
    )

    content = content.replace('\r\n', '\n')
    return content, (c1, c2, c3, c4, c5, c6)

def clean_redscripts_cache(game_dir):
    cleaned = 0
    search_dirs = [
        os.path.join(game_dir, "content"),
        os.path.join(game_dir, "Mods"),
        game_dir
    ]
    for root_search in search_dirs:
        if os.path.exists(root_search):
            for root_dir, _, files in os.walk(root_search):
                for fname in files:
                    if fname.lower().endswith(".redscripts"):
                        rpath = os.path.join(root_dir, fname)
                        try:
                            os.remove(rpath)
                            cleaned += 1
                        except OSError:
                            pass
    if cleaned > 0:
        print(f"[OK] Script cache cleared ({cleaned} .redscripts files).")

def install_witcher_mod(game_dir):
    mods_root = os.path.join(game_dir, "Mods")
    os.makedirs(mods_root, exist_ok=True)

    orig_pw = os.path.join(game_dir, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")
    bak_pw = orig_pw + ".bak"
    if not os.path.exists(bak_pw):
        shutil.copy2(orig_pw, bak_pw)

    source_file = bak_pw if os.path.exists(bak_pw) else orig_pw
    orig_content = read_ws_file(source_file)
    new_content, counts = inject_ws_code(orig_content)
    encoded_bytes = new_content.encode("utf-8-sig")

    mod_dir = os.path.join(mods_root, "modAutoOptiCutscene", "content", "scripts", "game", "player")
    os.makedirs(mod_dir, exist_ok=True)
    mod_pw = os.path.join(mod_dir, "playerWitcher.ws")
    with open(mod_pw, "wb") as f:
        f.write(encoded_bytes)
    print(f"[OK] Saved mod script: {mod_pw} (Hook count: {counts})")

    with open(orig_pw, "wb") as f:
        f.write(encoded_bytes)
    print(f"[OK] Updated base game script: {orig_pw}")

    clean_redscripts_cache(game_dir)

    for xml_name, group_id in (("hidden.xml", "Hidden"), ("gameplay.xml", "Gameplay")):
        xml_path = os.path.join(game_dir, "bin", "config", "r4game", "user_config_matrix", "pc", xml_name)
        xml_bak = xml_path + ".bak"
        if os.path.exists(xml_path):
            if not os.path.exists(xml_bak):
                try:
                    shutil.copy2(xml_path, xml_bak)
                except Exception:
                    pass

            xml_text = read_ws_file(xml_path)
            if 'id="OptiCutscene"' not in xml_text:
                xml_text, n = re.subn(
                    rf'(<Group\s+id="{group_id}"[^>]*>\s*<(?:Visible)?Vars>)',
                    r'\1\n\t\t\t<Var id="OptiCutscene" displayName="OptiCutscene" displayType="TOGGLE"/>',
                    xml_text,
                    count=1
                )
                if n > 0:
                    with open(xml_path, "wb") as f:
                        f.write(xml_text.encode("utf-8-sig"))
                    print(f"[OK] Registered OptiCutscene variable in {xml_name}")

def uninstall_witcher_mod(game_dir, config_folder):
    print("\n[*] Starting uninstallation of modAutoOptiCutscene...")
    mods_root = os.path.join(game_dir, "Mods", "modAutoOptiCutscene")
    if os.path.exists(mods_root):
        try:
            shutil.rmtree(mods_root)
            print("[OK] Removed mod directory: modAutoOptiCutscene")
        except Exception as e:
            print(f"[!] Error removing mod directory: {e}")

    orig_pw = os.path.join(game_dir, "content", "content0", "scripts", "game", "player", "playerWitcher.ws")
    bak_pw = orig_pw + ".bak"
    if os.path.exists(bak_pw):
        try:
            shutil.copy2(bak_pw, orig_pw)
            os.remove(bak_pw)
            print("[OK] Restored original playerWitcher.ws script in content0.")
        except Exception as e:
            print(f"[!] Error restoring playerWitcher.ws: {e}")

    for xml_name in ("hidden.xml", "gameplay.xml"):
        xml_path = os.path.join(game_dir, "bin", "config", "r4game", "user_config_matrix", "pc", xml_name)
        xml_bak = xml_path + ".bak"
        if os.path.exists(xml_bak):
            try:
                shutil.copy2(xml_bak, xml_path)
                os.remove(xml_bak)
                print(f"[OK] Restored original {xml_name} configuration file.")
            except Exception as e:
                print(f"[!] Error restoring {xml_name}: {e}")

    if config_folder and os.path.exists(config_folder):
        mods_ini = os.path.join(config_folder, "mods.settings")
        if os.path.exists(mods_ini):
            try:
                with open(mods_ini, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                new_text = re.sub(r'\[modAutoOptiCutscene\][^\[]*', '', text)
                with open(mods_ini, "w", encoding="utf-8") as f:
                    f.write(new_text.strip())
                print("[OK] Removed modAutoOptiCutscene entry from mods.settings.")
            except Exception:
                pass

    clean_redscripts_cache(game_dir)
    print("\n[SUCCESS] Uninstallation completed successfully. The game is back to vanilla state.\n")

def parse_settings_state(fpath):
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        matches = re.findall(r'(?:OptiCutscene|CutsceneActive)\s*=\s*([^\r\n]+)', text)
        if matches:
            last_val = matches[-1].strip().strip('"').lower()
            return last_val in ("1", "true")
    except OSError:
        pass
    return None

def _safe_mtime(fpath):
    try:
        return os.path.getmtime(fpath)
    except OSError:
        return 0

# =====================================================================
#  MAIN APPLICATION LOOP (PURE FILE ENGINE & STATE RESTORATION)
# =====================================================================
def main():
    set_console_title()
    disable_quickedit()
    print("=================================================================")
    print(f"   {SCRIPT_NAME}")
    print("=================================================================")
    ensure_admin()

    stored_cfg = load_stored_config()

    if "--uninstall" in sys.argv:
        gdir = stored_cfg.get("game_dir") or find_witcher3_folder(stored_cfg)
        cfg_dir = stored_cfg.get("user_config_dir") or resolve_user_config_folder(stored_cfg)
        if gdir:
            uninstall_witcher_mod(gdir, cfg_dir)
        else:
            print("[ERROR] Cannot locate game folder for uninstallation.")
        input("Press Enter to exit...")
        return

    if get_witcher_pid() is not None:
        print("\n[WARNING] The Witcher 3 is currently RUNNING!")
        print("Please close the game so the script can configure files and verify environment...")
        while get_witcher_pid() is not None:
            time.sleep(1.0)
        print("[OK] Game closed. Continuing...\n")

    # 1. Locate and validate game installation folder
    game_dir = find_witcher3_folder(stored_cfg)
    if not game_dir or not os.path.exists(game_dir):
        print("[CRITICAL ERROR] The Witcher 3 installation directory not found.")
        input("Press Enter to exit...")
        return

    print(f"[*] Game directory: {game_dir}")

    # 2. Locate user Documents configuration folder
    config_folder = resolve_user_config_folder(stored_cfg)
    if not config_folder:
        print("[CRITICAL ERROR] The Witcher 3 Documents configuration directory not found.")
        input("Press Enter to exit...")
        return

    print(f"[*] Player configuration directory: {config_folder}")

    # 3. Verify OptiScaler presence
    patcher = OptiScalerPatcher(game_dir)
    if not patcher.is_optiscaler_present():
        print("\n[WARNING] OptiScaler dxgi.dll was not found in bin\\x64_dx12!")
        print("Make sure OptiScaler is properly installed in your game directory.")

    # 4. Clean OptiScaler.ini and apply temporary micro-patch
    cleanup_optiscaler_ini(game_dir)
    patcher.apply_disk_patch()

    def cleanup_on_exit():
        patcher.restore_disk_patch()

    atexit.register(cleanup_on_exit)

    def signal_handler(sig, frame):
        cleanup_on_exit()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception:
        pass

    try:
        # 5. Install WitcherScript hooks & prepare .settings files
        install_witcher_mod(game_dir)
        settings_files = get_settings_files(config_folder)
        prepare_settings_files(settings_files, config_folder)

        # 6. Initialize Win32 bridge & state machines
        bridge = OptiScalerDirectBridge(game_dir)
        hotkey_tracker = PlayerHotkeyTracker(bridge.vk_code)

        print("\n[*] SYSTEM READY FOR GAMEPLAY! Launch the game and load your save.")
        print(f"  -> In-game notification on load: '{INGAME_NOTIFICATION}'")
        print(f"  -> Tracking player hotkey: {hex(bridge.vk_code)} (State Restoration: ACTIVE)")
        print("  -> Alt-Tab suspension / Anti-flicker hysteresis: ACTIVE")
        print("  -> High-performance file monitor: ACTIVE\n")
        print("  [Hint] To uninstall the mod in the future, run this script with --uninstall.\n")

        pid = None
        h_process = None

        optiscaler_current_state = bridge.initial_state
        in_cutscene = False
        pre_cutscene_state = optiscaler_current_state
        file_connected = False
        last_mtimes = {f: _safe_mtime(f) for f in settings_files}

        while True:
            # =============================================================
            #  PHASE 1: Standby — poll for witcher3.exe process every 3s
            # =============================================================
            if h_process is None:
                time.sleep(3.0)
                new_pid = get_witcher_pid()
                if new_pid is not None:
                    new_h = kernel32.OpenProcess(
                        PROCESS_QUERY_INFORMATION | SYNCHRONIZE,
                        False, new_pid
                    )
                    if new_h:
                        pid = new_pid
                        h_process = new_h
                        optiscaler_current_state = bridge.initial_state
                        in_cutscene = False
                        pre_cutscene_state = optiscaler_current_state
                        file_connected = False
                        bridge.cached_hwnds = []
                        bridge.last_pid = None
                        for f in settings_files:
                            last_mtimes[f] = _safe_mtime(f)

                        print(f"[*] Detected witcher3.exe process (PID: {pid}). Monitoring active...")
                continue

            # =============================================================
            #  WINDOW FOCUS VERIFICATION (ALT-TAB SUSPENSION)
            # =============================================================
            is_game_foreground = bridge.is_game_foreground(pid)
            if not is_game_foreground:
                ret = kernel32.WaitForSingleObject(h_process, 500)
                if ret != WAIT_TIMEOUT:
                    kernel32.CloseHandle(h_process)
                    print(f"[*] Game process (PID: {pid}) terminated.")
                    h_process = None
                    pid = None
                    patcher.restore_disk_patch()
                    continue
                continue

            # =============================================================
            #  PLAYER HOTKEY TRACKING (GetAsyncKeyState with Debouncing)
            # =============================================================
            if hotkey_tracker.check_player_toggle(is_game_foreground, bridge.last_simulated_time):
                optiscaler_current_state = not optiscaler_current_state
                state_str = "ENABLED (ON)" if optiscaler_current_state else "DISABLED (OFF)"
                print(f"[HOTKEY] Player manually toggled OptiScaler -> {state_str}")
                if not in_cutscene:
                    pre_cutscene_state = optiscaler_current_state

            # =============================================================
            #  ACTIVE MONITORING: PURE HIGH-SPEED FILE CHANNEL (< 80ms)
            # =============================================================
            ret = kernel32.WaitForSingleObject(h_process, 80)
            if ret != WAIT_TIMEOUT:
                kernel32.CloseHandle(h_process)
                print(f"[*] Game process (PID: {pid}) terminated.")
                h_process = None
                pid = None
                patcher.restore_disk_patch()
                continue

            detected_file_state = None

            for fpath in settings_files:
                mtime = _safe_mtime(fpath)
                if mtime != last_mtimes.get(fpath, 0):
                    last_mtimes[fpath] = mtime
                    f_state = parse_settings_state(fpath)
                    if f_state is not None:
                        detected_file_state = f_state
                        if not file_connected:
                            file_connected = True
                            print(f"[CONNECTED] Received game state signal ({os.path.basename(fpath)})!")

            if detected_file_state is not None:
                if detected_file_state:
                    # Cutscene / dialogue started
                    if not in_cutscene:
                        in_cutscene = True
                        pre_cutscene_state = optiscaler_current_state
                        if not pre_cutscene_state:
                            mode_used = bridge.toggle_optiscaler(pid)
                            optiscaler_current_state = True
                            print(f"[+] Cutscene / dialogue -> DLSS ENABLED [{mode_used}] (Saved pre-scene state: OFF)")
                        else:
                            print(f"[=] Cutscene / dialogue -> DLSS KEPT ENABLED (Player enabled it during gameplay)")
                else:
                    # Return to gameplay
                    if in_cutscene:
                        in_cutscene = False
                        if not pre_cutscene_state:
                            if optiscaler_current_state:
                                mode_used = bridge.toggle_optiscaler(pid)
                                optiscaler_current_state = False
                                print(f"[-] Returning to gameplay -> DLSS RESTORED TO DISABLED [{mode_used}] (State Restoration)")
                        else:
                            print(f"[=] Returning to gameplay -> DLSS KEPT ENABLED (Player preference preserved)")

    finally:
        patcher.restore_disk_patch()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n[CRITICAL SCRIPT ERROR]:")
        traceback.print_exc()
        input("\nPress Enter to exit...")
