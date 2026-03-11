import sqlite3
from core.output_normalizer import OutputNormalizer


class CookiesParser:
    """
    Parses Chrome/Chromium Cookies SQLite database.
    """

    def __init__(self):
        self.normalizer = OutputNormalizer()

    def parse(self, db_path: str):
        print("[*] Parsing Chrome Cookies...")

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
            SELECT
                host_key,
                name,
                path,
                expires_utc,
                is_secure,
                is_httponly
            FROM cookies
            ORDER BY host_key ASC;
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            normalized = self.normalizer.normalize_sql_rows(rows)

            # Convert Chrome timestamps
            for entry in normalized:
                entry["expires_utc"] = self._chrome_time_to_unix(entry["expires_utc"])

            return {
                "db_path": db_path,
                "cookies": normalized,
                "count": len(normalized),
            }

        except Exception as e:
            return {
                "db_path": db_path,
                "error": str(e),
                "cookies": [],
            }

    def _chrome_time_to_unix(self, chrome_time):
        try:
            return (chrome_time / 1_000_000) - 11644473600
        except:
            return None
