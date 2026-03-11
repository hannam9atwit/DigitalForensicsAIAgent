import subprocess
import re

def detect_ntfs_offset(image_path: str) -> int:
    """
    Runs mmls on the disk image and extracts the NTFS partition offset.
    Returns the offset in sectors (int).
    """

    try:
        result = subprocess.run(
            ["bin/sleuthkit/mmls.exe", image_path],
            capture_output=True,
            text=True,
            shell=False
        )
    except Exception as e:
        print("[!] Failed to run mmls:", e)
        return 0

    output = result.stdout

    # Look for NTFS or 0x07 partition
    for line in output.splitlines():
        if "NTFS" in line or "0x07" in line:
            parts = line.split()
            # Start sector is the 2nd column
            try:
                start_sector = int(parts[2])
                print(f"[+] Detected NTFS partition offset: {start_sector}")
                return start_sector
            except:
                continue

    print("[!] No NTFS partition found, using offset 0")
    return 0
