import sqlite3
from core.output_normalizer import OutputNormalizer


class HistoryParser:
    """
    Parses Chrome/Chromium History SQLite database.
    """

    def __init__(self):
        self.normalizer = OutputNormalizer()

    def parse(self, db_path: str):
        print("[*] Parsing Chrome History...")

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
            SELECT 
                urls.url,
                urls.title,
                urls.visit_count,
                urls.typed_count,
                visits.visit_time,
                visits.transition
            FROM urls
            JOIN visits ON urls.id = visits.url
            ORDER BY visits.visit_time ASC;
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            normalized = self.normalizer.normalize_sql_rows(rows)

            # Convert Chrome timestamps (microseconds since 1601)
            for entry in normalized:
                entry["visit_time"] = self._chrome_time_to_unix(entry["visit_time"])

            return {
                "db_path": db_path,
                "visits": normalized,
                "count": len(normalized),
            }

        except Exception as e:
            return {
                "db_path": db_path,
                "error": str(e),
                "visits": [],
            }

    def _chrome_time_to_unix(self, chrome_time):
        """
        Chrome timestamps = microseconds since Jan 1, 1601.
        Convert to Unix epoch seconds.
        """
        try:
            unix_time = (chrome_time / 1_000_000) - 11644473600
            return unix_time
        except:
            return None
