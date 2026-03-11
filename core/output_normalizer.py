import csv
import re
from typing import Any, Dict, List


class OutputNormalizer:
    """
    Converts raw Sleuth Kit and SQLite output into structured JSON.
    """

    # ---------------------------------------------------------
    # Normalize fls output (file listing, including deleted files)
    # ---------------------------------------------------------
    def normalize_fls(self, raw_output: str) -> List[Dict[str, Any]]:
        """
        Example fls line:
        r/r 128-128-3: $MFT
        d/d 256-256-5: Users
        r/r 512-512-1: secret.docx (deleted)
        """

        entries = []
        lines = raw_output.splitlines()

        fls_pattern = re.compile(
            r"(?P<type>[dr]/[dr])\s+"
            r"(?P<inode>\d+(?:-\d+)*):\s+"
            r"(?P<name>.+?)(?:\s+\((?P<flags>.+)\))?$"
        )

        for line in lines:
            match = fls_pattern.match(line.strip())
            if not match:
                continue

            entry = {
                "type": match.group("type"),
                "inode": match.group("inode"),
                "name": match.group("name"),
                "deleted": False,
                "raw": line.strip(),
            }

            flags = match.group("flags")
            if flags and "deleted" in flags.lower():
                entry["deleted"] = True

            entries.append(entry)

        return entries

    # ---------------------------------------------------------
    # Normalize istat output (metadata for a single inode)
    # ---------------------------------------------------------
    def normalize_istat(self, raw_output: str) -> Dict[str, Any]:
        """
        Example istat output contains:
        - Size
        - Allocated
        - Created/Modified/Accessed timestamps
        """

        data = {
            "size": None,
            "allocated": None,
            "timestamps": {},
            "raw": raw_output,
        }

        for line in raw_output.splitlines():
            line = line.strip()

            if line.startswith("Size:"):
                data["size"] = int(line.split()[1])

            if line.startswith("Allocated:"):
                data["allocated"] = line.split()[1]

            if "Created:" in line:
                data["timestamps"]["created"] = line.split("Created:")[1].strip()

            if "File Modified:" in line:
                data["timestamps"]["modified"] = line.split("File Modified:")[1].strip()

            if "Accessed:" in line:
                data["timestamps"]["accessed"] = line.split("Accessed:")[1].strip()

        return data

    # ---------------------------------------------------------
    # Normalize mactime CSV
    # ---------------------------------------------------------
    def normalize_mactime(self, csv_text: str) -> List[Dict[str, Any]]:
        """
        mactime output is CSV-like:
        Date,Size,Type,Mode,UID,GID,Inode,File Name
        """

        events = []
        reader = csv.reader(csv_text.splitlines())

        for row in reader:
            if len(row) < 8:
                continue

            event = {
                "date": row[0],
                "size": row[1],
                "type": row[2],
                "mode": row[3],
                "uid": row[4],
                "gid": row[5],
                "inode": row[6],
                "filename": row[7],
            }
            events.append(event)

        return events

    # ---------------------------------------------------------
    # Normalize SQLite rows
    # ---------------------------------------------------------
    def normalize_sql_rows(self, rows) -> List[Dict[str, Any]]:
        """
        Converts sqlite3.Row objects into plain dicts.
        """
        normalized = []
        for row in rows:
            if hasattr(row, "keys"):
                normalized.append(dict(row))
            else:
                normalized.append({"value": row})
        return normalized
