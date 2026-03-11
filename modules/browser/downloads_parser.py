import sqlite3
from core.output_normalizer import OutputNormalizer


class DownloadsParser:
    """
    Parses Chrome/Chromium Downloads table.
    """

    def __init__(self):
        self.normalizer = OutputNormalizer()

    def parse(self, db_path: str):
        print("[*] Parsing Chrome Downloads...")

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
            SELECT
                downloads.id,
                downloads.target_path,
                downloads.start_time,
                downloads.end_time,
                downloads.received_bytes,
                downloads.total_bytes,
                downloads.danger_type,
                downloads.interrupt_reason,
                downloads_url_chains.url AS referrer
            FROM downloads
            LEFT JOIN downloads_url_chains
                ON downloads.id = downloads_url_chains.id
            ORDER BY downloads.start_time ASC;
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            normalized = self.normalizer.normalize_sql_rows(rows)

            # Convert Chrome timestamps
            for entry in normalized:
                entry["start_time"] = self._chrome_time_to_unix(entry["start_time"])
                entry["end_time"] = self._chrome_time_to_unix(entry["end_time"])

            return {
                "db_path": db_path,
                "downloads": normalized,
                "count": len(normalized),
            }

        except Exception as e:
            return {
                "db_path": db_path,
                "error": str(e),
                "downloads": [],
            }

    def _chrome_time_to_unix(self, chrome_time):
        try:
            return (chrome_time / 1_000_000) - 11644473600
        except:
            return None
