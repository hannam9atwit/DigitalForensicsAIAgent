import os
import subprocess
import shutil
import sys


def _norm(path: str) -> str:
    """Absolute path with OS-native separators (backslashes on Windows)."""
    return os.path.normpath(os.path.abspath(path))


class ToolRunner:

    def __init__(self):
        # sys._MEIPASS is set by PyInstaller to the folder where it extracts
        # bundled files at runtime. Fall back to the project root when running
        # from source so both modes work with the same code.
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.tsk_path = os.path.join(base, "bin", "sleuthkit")
        print(f"[DEBUG] ToolRunner base     : {base}")
        print(f"[DEBUG] ToolRunner tsk_path : {self.tsk_path}")
        print(f"[DEBUG] tsk_path exists     : {os.path.exists(self.tsk_path)}")
        if os.path.exists(self.tsk_path):
            print(f"[DEBUG] tsk_path contents   : {os.listdir(self.tsk_path)}")

    def _resolve(self, tool_name: str):
        for candidate in [
            os.path.join(self.tsk_path, tool_name + ".exe"),
            os.path.join(self.tsk_path, tool_name),
        ]:
            if os.path.exists(candidate):
                print(f"[DEBUG] Resolved {tool_name} -> {candidate}")
                return candidate

        # Last resort: check system PATH
        found = shutil.which(tool_name)
        if found:
            print(f"[DEBUG] Resolved {tool_name} from PATH -> {found}")
        else:
            print(f"[!] Could not resolve tool: {tool_name}")
            print(f"    Looked in: {self.tsk_path}")
        return found

    def run_tsk(self, cmd_list: list, image_path: str = None) -> dict:
        tool      = cmd_list[0]
        tool_path = self._resolve(tool)

        if not tool_path:
            return {
                "stdout":     "",
                "stderr":     f"Tool not found: {tool} (looked in {self.tsk_path})",
                "returncode": -1,
            }

        cmd = [tool_path] + cmd_list[1:]

        if image_path:
            normed = _norm(image_path)
            cmd = [normed if arg == image_path else arg for arg in cmd]

            if self._is_ewf(normed) and "-i" not in cmd:
                cmd = [cmd[0], "-i", "ewf"] + cmd[1:]

        print(f"[DEBUG] Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            return {
                "stdout":     result.stdout,
                "stderr":     result.stderr,
                "returncode": result.returncode,
            }
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "returncode": -1}

    @staticmethod
    def _is_ewf(path: str) -> bool:
        return os.path.splitext(path)[1].lower() == ".e01"