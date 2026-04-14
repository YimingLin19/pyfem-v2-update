"""run_case 脚本集成测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.io import JsonResultsReader


class RunCaseScriptTests(unittest.TestCase):
    """验证可编辑配置脚本可以直接驱动 INP 求解。"""

    def test_run_case_script_writes_results_and_vtk(self) -> None:
        root = Path(__file__).resolve().parents[2]
        inp_path = root / "tests" / f"_tmp_run_case_{uuid4().hex}.inp"
        results_path = root / "tests" / f"_tmp_run_case_{uuid4().hex}.json"
        vtk_path = root / "tests" / f"_tmp_run_case_{uuid4().hex}.vtk"
        report_path = root / "tests" / f"_tmp_run_case_{uuid4().hex}.report.json"
        try:
            inp_path.write_text(
                """
*Heading
Task 08 run_case script example
*Node
1, 0.0, 0.0
2, 2.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Density
4.0
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=LOAD_STEP
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -12.0
*End Step
""".strip(),
                encoding="utf-8",
            )

            env = dict(os.environ)
            env["PYFEM_INP_PATH"] = str(inp_path)
            env["PYFEM_RESULTS_PATH"] = str(results_path)
            env["PYFEM_VTK_PATH"] = str(vtk_path)
            env["PYFEM_REPORT_PATH"] = str(report_path)
            env["PYFEM_WRITE_VTK"] = "1"

            completed = subprocess.run(
                [sys.executable, str(root / "run_case.py")],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}")
            self.assertTrue(results_path.exists())
            self.assertTrue(vtk_path.exists())
            self.assertTrue(report_path.exists())

            reader = JsonResultsReader(results_path)
            frame = reader.find_frame("LOAD_STEP", 0)
            self.assertAlmostEqual(frame.get_field("U").values["part-1.2"]["UY"], -0.16, places=12)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["step_name"], "LOAD_STEP")
            self.assertEqual(payload["results_path"], str(results_path))
            self.assertEqual(payload["frame_count"], 1)
            self.assertIn("results =", completed.stdout)
            self.assertIn("vtk =", completed.stdout)
            self.assertIn("report =", completed.stdout)
        finally:
            inp_path.unlink(missing_ok=True)
            results_path.unlink(missing_ok=True)
            vtk_path.unlink(missing_ok=True)
            report_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
