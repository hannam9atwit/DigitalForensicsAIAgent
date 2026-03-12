import os
import subprocess
import shutil
import sys

class ToolRunner:
    """
    Runs Sleuth Kit tools from the bundled /bin/sleuthkit folder.
    """

    def __init__(self):
        # Path to project root
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(__file__)))
        # Path to bundled TSK binaries
        self.tsk_path = os.path.join(base_dir, "bin", "sleuthkit")

    def _resolve(self, tool_name):
        """
        Returns the full path to the tool (e.g., fls.exe).
        """
        exe = tool_name + ".exe"
        full_path = os.path.join(self.tsk_path, exe)

        if os.path.exists(full_path):
            return full_path

        # fallback: try system PATH
        return shutil.which(tool_name)

    def run_tsk(self, cmd_list):
        """
        Runs a Sleuth Kit command using bundled binaries.
        """
        tool = cmd_list[0]
        tool_path = self._resolve(tool)

        if not tool_path:
            return {
                "stdout": "",
                "stderr": f"Tool not found: {tool}",
                "returncode": -1
            }

        # Replace tool name with full path
        cmd_list = [tool_path] + cmd_list[1:]

        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                shell=False
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }
