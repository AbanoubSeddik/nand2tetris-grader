"""
Local CLI for grading a single nand2tetris submission without Moodle/Telegram.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import zipfile
from pathlib import Path

import ai_report as ai
from config import get_project
from grading_engine import grade_student


def _expected_zip_name(student_name: str, project_num: int) -> str:
    parts = student_name.strip().split()
    first = parts[0] if parts else "Unknown"
    last = parts[-1] if len(parts) > 1 else "Student"
    stems = {
        1: "HW1_Gates",
        2: "HW2_ALU",
        3: "HW3_Memory",
        4: "HW4_Assembly",
        5: "HW5_Computer",
    }
    stem = stems.get(project_num, f"HW{project_num}")
    return f"{stem}_{first}_{last}.zip"


def _bundle_input(input_path: Path, project_num: int, student_name: str):
    project = get_project(project_num)
    expected_ext = project["file_ext"]

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    suffixes = [s.lower() for s in input_path.suffixes]
    if suffixes and suffixes[-1] in {".zip", ".rar"}:
        return str(input_path), input_path.name, None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = Path(tmp.name)
    tmp.close()

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if input_path.is_dir():
            files = sorted(
                p for p in input_path.rglob("*")
                if p.is_file() and p.suffix.lower() == expected_ext
            )
            if not files:
                raise ValueError(
                    f"No {expected_ext} files found in directory: {input_path}"
                )
            for file_path in files:
                zf.write(file_path, arcname=file_path.name)
        elif input_path.is_file():
            if input_path.suffix.lower() != expected_ext:
                raise ValueError(
                    f"Expected a {expected_ext}, .zip, .rar, or directory; got "
                    f"{input_path.name}"
                )
            zf.write(input_path, arcname=input_path.name)
        else:
            raise ValueError(f"Unsupported input: {input_path}")

    return str(tmp_path), _expected_zip_name(student_name, project_num), str(tmp_path)


async def _run(args) -> int:
    project = get_project(args.project)

    issues = []
    if not project["simulator_path"].exists():
        issues.append(f"Missing simulator: {project['simulator_path']}")
    if not project["test_path"].exists():
        issues.append(f"Missing test directory: {project['test_path']}")
    elif not list(project["test_path"].glob("*.tst")):
        issues.append(f"No .tst files found in: {project['test_path']}")

    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 2

    temp_bundle = None
    try:
        grade_input, zip_name, temp_bundle = _bundle_input(
            Path(args.input), args.project, args.student_name
        )
        result = await grade_student(
            grade_input,
            args.student_name,
            args.user_id,
            project_num=args.project,
            zip_filename=zip_name,
        )
        report = await ai.generate_report(result)
    finally:
        if temp_bundle:
            Path(temp_bundle).unlink(missing_ok=True)

    print(ai.format_header(result))
    print()
    print(report)

    if args.report_file:
        Path(args.report_file).write_text(report + "\n", encoding="utf-8")
        print()
        print(f"Report saved to {args.report_file}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Grade one local submission and print the feedback report without "
            "using Moodle or Telegram."
        )
    )
    parser.add_argument(
        "input",
        help="Path to a .zip/.rar submission, a single source file, or a directory.",
    )
    parser.add_argument(
        "--student-name",
        required=True,
        help="Student full name used in the report and zip-name checks.",
    )
    parser.add_argument(
        "--project",
        type=int,
        required=True,
        help="Homework number (1-5). For HW4 use --project 4.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=0,
        help="Optional numeric ID stored in the grading result. Default: 0.",
    )
    parser.add_argument(
        "--report-file",
        help="Optional path to save only the generated feedback text.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
