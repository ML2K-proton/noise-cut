"""Bundled VB-CABLE installer: verify, extract and run elevated."""

import ctypes
import hashlib
import os
import shutil
import tempfile
import zipfile
from ctypes import wintypes

import sounddevice as sd

from .config import resource_path

VENDOR_ZIP_NAME = "VBCABLE_Driver_Pack45.zip"
VENDOR_ZIP_SHA256 = "b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb"
INSTALLER_X64 = "VBCABLE_Setup_x64.exe"
INSTALL_ARGS = "-i -h"

WAIT_TIMEOUT_MS = 300_000
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_SHOWNORMAL = 1
ERROR_CANCELLED = 1223
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def vendor_zip_path() -> str:
    return resource_path("noisecut", "vendor", VENDOR_ZIP_NAME)


def installed() -> bool:
    """True when both CABLE Input and CABLE Output endpoints exist."""
    try:
        names = [dev["name"].lower() for dev in sd.query_devices()]
    except Exception:
        return False
    return any("cable input" in n for n in names) and any(
        "cable output" in n for n in names
    )


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare() -> str:
    """Verify the bundled package, extract it and return the installer path."""
    zip_path = vendor_zip_path()
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"Không tìm thấy gói VB-CABLE: {zip_path}")
    if _sha256(zip_path) != VENDOR_ZIP_SHA256:
        raise ValueError("Gói VB-CABLE bị hỏng hoặc không đúng phiên bản.")

    dest = os.path.join(tempfile.gettempdir(), "noise-cut-vbcable")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)

    installer = os.path.join(dest, INSTALLER_X64)
    if not os.path.isfile(installer):
        raise FileNotFoundError(f"Không tìm thấy {INSTALLER_X64} trong gói.")
    return installer


def _run_elevated(executable: str, parameters: str) -> int:
    """Run with UAC elevation and wait. Raises PermissionError if cancelled."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    hr = ole32.CoInitializeEx(None, 0x2)
    com_ready = hr is not None and hr >= 0  # S_OK (0) or S_FALSE (1)
    try:
        info = _SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = executable
        info.lpParameters = parameters
        info.lpDirectory = os.path.dirname(executable)
        info.nShow = SW_SHOWNORMAL

        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()
            if error == ERROR_CANCELLED:
                raise PermissionError("Bạn đã huỷ hộp thoại cấp quyền (UAC).")
            raise OSError(error, "Không chạy được bộ cài VB-CABLE.")

        try:
            result = kernel32.WaitForSingleObject(info.hProcess, WAIT_TIMEOUT_MS)
            if result == WAIT_TIMEOUT:
                return -1
            if result != WAIT_OBJECT_0:
                raise OSError("Lỗi khi chờ bộ cài VB-CABLE.")
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
                raise OSError("Không đọc được kết quả bộ cài VB-CABLE.")
            return int(exit_code.value)
        finally:
            if info.hProcess:
                kernel32.CloseHandle(info.hProcess)
    finally:
        if com_ready:
            ole32.CoUninitialize()


def install() -> tuple[bool, str]:
    """Extract and install VB-CABLE. Returns (ok, message)."""
    try:
        installer = prepare()
    except Exception as exc:
        return False, str(exc)

    try:
        code = _run_elevated(installer, INSTALL_ARGS)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Không cài được VB-CABLE: {exc}"

    if code == -1:
        return False, (
            "Bộ cài VB-CABLE vẫn đang chạy hoặc chưa kết thúc.\n"
            "Hãy kiểm tra cửa sổ cài đặt rồi thử lại."
        )
    if code != 0:
        return False, f"Bộ cài VB-CABLE báo lỗi (mã {code})."

    return True, "Cài VB-CABLE thành công. Cần khởi động lại Windows."
