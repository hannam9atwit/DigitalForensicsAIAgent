import os
import subprocess
import shutil
import sys


def _norm(path: str) -> str:
    """Absolute path with OS-native separators (backslashes on Windows)."""
    return os.path.normpath(os.path.abspath(path))


class ToolRunner:

    def __init__(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
        self.tsk_path = os.path.join(base, "bin", "sleuthkit")

    def _resolve(self, tool_name: str):
        for candidate in [
            os.path.join(self.tsk_path, tool_name + ".exe"),
            os.path.join(self.tsk_path, tool_name),
        ]:
            if os.path.exists(candidate):
                return candidate
        return shutil.which(tool_name)

    def run_tsk(self, cmd_list: list, image_path: str = None) -> dict:
        """
        Run a SleuthKit command.
        image_path is used to:
          • decide whether to inject -i ewf
          • normalise the path in cmd_list that matches the image
        """
        tool      = cmd_list[0]
        tool_path = self._resolve(tool)

        if not tool_path:
            return {"stdout": "", "stderr": f"Tool not found: {tool}", "returncode": -1}

        cmd = [tool_path] + cmd_list[1:]

        # Normalise any occurrence of the image path inside the command
        # (it's always the last positional argument in TSK commands)
        if image_path:
            normed = _norm(image_path)
            cmd = [normed if arg == image_path else arg for arg in cmd]

            # Inject -i ewf for E01 images if not already present
            if self._is_ewf(normed) and "-i" not in cmd:
                # Insert right after the binary: tool -i ewf [rest...]
                cmd = [cmd[0], "-i", "ewf"] + cmd[1:]

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