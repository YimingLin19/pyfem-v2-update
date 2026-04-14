"""代码汇总脚本集成测试。"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4


class ExportCodeBundleScriptTests(unittest.TestCase):
    """验证代码汇总脚本能够生成纯文本代码包。"""

    def test_export_script_writes_text_without_markdown(self) -> None:
        root = Path(__file__).resolve().parents[2]
        output_path = root / "tests" / f"_tmp_code_bundle_{uuid4().hex}.txt"
        env = os.environ.copy()
        env["PYFEM_EXPORT_OUTPUT_PATH"] = str(output_path)

        completed = subprocess.run(
            [sys.executable, str(root / "export_code_bundle.py")],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        try:
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            self.assertTrue(output_path.exists())
            text = output_path.read_text(encoding="utf-8")
            file_lines = {line for line in text.splitlines() if line.startswith("FILE: ")}
            self.assertIn("FILE: export_code_bundle.py", file_lines)
            self.assertIn("FILE: run_case.py", file_lines)
            self.assertIn("FILE: src/pyfem/compiler/compiler.py", file_lines)
            self.assertNotIn("FILE: docs/Architecture_Overview.md", file_lines)
            self.assertNotIn("FILE: Prompt.md", file_lines)
            self.assertNotIn("FILE: Job-1.results.json", file_lines)
        finally:
            if output_path.exists():
                output_path.unlink()


if __name__ == "__main__":
    unittest.main()
