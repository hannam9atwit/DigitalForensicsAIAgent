import os
import subprocess
import shutil
import sys
import tempfile


def _tsk_bin(name: str) -> str:
    base    = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
    tsk_dir = os.path.join(base, "bin", "sleuthkit")
    for candidate in [
        os.path.join(tsk_dir, name + ".exe"),
        os.path.join(tsk_dir, name),
    ]:
        if os.path.exists(candidate):
            return candidate
    return shutil.which(name) or name


def _norm(path: str) -> str:
    """
    Resolve to an absolute, OS-native path.
    On Windows: converts any forward slashes to backslashes so that
    libewf's internal glob (which calls _wstat / FindFirstFile) works
    correctly. Mixed slashes like C:\\foo/bar.E01 break it silently.
    """
    return os.path.normpath(os.path.abspath(path))


def _run(cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          shell=False, timeout=timeout)


def _parse_ntfs_offset(mmls_output: str) -> int:
    for line in mmls_output.splitlines():
        if "NTFS" in line or "0x07" in line or "Basic data" in line:
            parts = line.split()
            for idx in (2, 1, 3):
                try:
                    val = int(parts[idx].rstrip(":"))
                    if val >= 0:
                        print(f"[+] NTFS partition offset: {val} sectors")
                        return val
                except (ValueError, IndexError):
                    continue
    print("[!] No NTFS partition found — using offset 0")
    return 0


# ── Public API ────────────────────────────────────────────────────────────────

def detect_ntfs_offset(image_path: str) -> int:
    """Return NTFS partition start offset in sectors."""
    image_path = _norm(image_path)
    ext        = os.path.splitext(image_path)[1].lower()
    if ext == ".e01":
        return _detect_e01(image_path)
    return _detect_raw(image_path)


def is_ewf(image_path: str) -> bool:
    return os.path.splitext(image_path)[1].lower() == ".e01"


# ── Internal ──────────────────────────────────────────────────────────────────

def _detect_raw(image_path: str) -> int:
    try:
        r = _run([_tsk_bin("mmls"), image_path])
        if r.returncode == 0 and r.stdout:
            return _parse_ntfs_offset(r.stdout)
        print(f"[!] mmls error: {r.stderr.strip()}")
    except Exception as e:
        print(f"[!] mmls failed: {e}")
    return 0


def _detect_e01(image_path: str) -> int:
    """Try mmls directly (works when TSK built with libewf), else ewfexport fallback."""
    try:
        r = _run([_tsk_bin("mmls"), image_path])
        if r.returncode == 0 and r.stdout.strip():
            print("[+] mmls read E01 directly (libewf confirmed)")
            return _parse_ntfs_offset(r.stdout)
        stderr = r.stderr.strip()
        print(f"[~] mmls direct E01 failed ({stderr}) — trying ewfexport fallback")
    except Exception as e:
        print(f"[~] mmls E01 exception: {e} — trying ewfexport fallback")

    return _detect_e01_via_export(image_path)


def _detect_e01_via_export(image_path: str) -> int:
    ewfexport = shutil.which("ewfexport") or shutil.which("ewfexport.exe")
    if not ewfexport:
        print(
            "[!] ewfexport not found.\n"
            "    Your SleuthKit binaries need libewf support to read E01 files.\n"
            "    Windows: get libewf-enabled TSK from "
            "https://github.com/msuhanov/TSK-win-libewf/releases\n"
            "    Linux:   sudo apt install ewf-tools sleuthkit"
        )
        return 0

    tmp_dir  = tempfile.mkdtemp(prefix="forensic_e01_")
    raw_path = os.path.join(tmp_dir, "exported")
    try:
        print("[*] Exporting E01 via ewfexport (may take a moment)...")
        r = _run([ewfexport, "-f", "raw", "-t", raw_path, image_path], timeout=120)
        if r.returncode != 0:
            print(f"[!] ewfexport failed: {r.stderr.strip()}")
            return 0
        actual = raw_path if os.path.exists(raw_path) else raw_path + ".raw"
        if not os.path.exists(actual):
            print(f"[!] ewfexport output not found at {actual}")
            return 0
        return _detect_raw(actual)
    except Exception as e:
        print(f"[!] E01 export failed: {e}")
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)