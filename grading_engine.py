"""
Core grading: extract zip, match files, run simulator, partial credit.
"""

import os
import re
import shutil
import zipfile
import asyncio
import tempfile
import subprocess
import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import get_project, ACTIVE_PROJECT, PROJECTS

log = logging.getLogger(__name__)


@dataclass
class FileMatch:
    expected_name: str
    actual_filename: str
    match_type: str  # exact|case_fix|fuzzy|not_found
    issue: str = ""


@dataclass
class ZipNaming:
    original_filename: str
    is_correct: bool
    expected_pattern: str = ""
    issue: str = ""


@dataclass
class ChipResult:
    name: str
    passed: bool
    points: float
    max_points: float
    error_type: str = ""
    error_msg: str = ""
    fail_line: int = 0
    expected: str = ""
    actual: str = ""
    total_tests: int = 0
    passed_tests: int = 0


@dataclass
class GradingResult:
    student_name: str
    user_id: int
    project_num: int = ACTIVE_PROJECT
    chips: list[ChipResult] = field(default_factory=list)
    total_earned: float = 0.0
    total_possible: float = 0.0
    warnings: list[str] = field(default_factory=list)
    file_matches: list[FileMatch] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)
    zip_naming: ZipNaming = None

    @property
    def percentage(self):
        return round(self.total_earned / self.total_possible * 100, 1) \
            if self.total_possible else 0.0

    @property
    def passed_names(self):
        return [c.name for c in self.chips if c.passed]

    @property
    def failed(self):
        return [c for c in self.chips if not c.passed]

    @property
    def naming_issues(self):
        return [m for m in self.file_matches if m.match_type != "exact"]

    @property
    def has_naming_issues(self):
        return len(self.naming_issues) > 0 or \
            (self.zip_naming and not self.zip_naming.is_correct)


# ── Zip Naming Check ─────────────────────────────────────────

def check_zip_naming(
    filename: str,
    student_name: str,
    project_num: int,
) -> ZipNaming:
    """Check if zip filename follows the expected convention."""
    proj = get_project(project_num)
    pattern = proj.get("zip_pattern", "")

    if not filename:
        return ZipNaming(
            original_filename="", is_correct=False,
            expected_pattern=pattern,
            issue="No filename available")

    name_no_ext = filename
    if name_no_ext.lower().endswith(".zip"):
        name_no_ext = name_no_ext[:-4]

    # Build expected name from student name
    name_parts = student_name.strip().split()
    if len(name_parts) >= 2:
        first = name_parts[0]
        last = name_parts[-1]
    elif len(name_parts) == 1:
        first = name_parts[0]
        last = ""
    else:
        first = "Unknown"
        last = "Student"

    # Expected patterns for each project
    expected_patterns = {
        1: f"HW1_Gates_{first}_{last}",
        2: f"HW2_ALU_{first}_{last}",
        3: f"HW3_Memory_{first}_{last}",
        4: f"HW4_Assembly_{first}_{last}",
        5: f"HW5_Computer_{first}_{last}",
    }

    expected = expected_patterns.get(project_num,
                                     f"HW{project_num}_{first}_{last}")

    # Check exact match
    if name_no_ext == expected:
        return ZipNaming(
            original_filename=filename, is_correct=True,
            expected_pattern=f"{expected}.zip")

    # Check if it at least contains HW number
    hw_num_present = bool(
        re.search(rf'(?:hw|homework)\s*{project_num}', name_no_ext,
                  re.IGNORECASE))

    # Check if student name is present (case insensitive)
    name_present = (
        first.lower() in name_no_ext.lower() or
        last.lower() in name_no_ext.lower() if last else
        first.lower() in name_no_ext.lower()
    )

    issues = []
    if not hw_num_present:
        issues.append("missing homework number")
    if not name_present:
        issues.append("missing your name")

    if issues:
        issue = (
            f"Zip named '{filename}' -- should be "
            f"'{expected}.zip' ({', '.join(issues)})")
    else:
        issue = (
            f"Zip named '{filename}' -- should be "
            f"'{expected}.zip'")

    return ZipNaming(
        original_filename=filename,
        is_correct=False,
        expected_pattern=f"{expected}.zip",
        issue=issue)


# ── File Matching ────────────────────────────────────────────

def _normalize(name):
    name = name.strip()
    name = re.sub(r'\s*\(\d+\)\s*', '', name)
    name = re.sub(r'\s*copy\s*\d*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\s_\-]+', '', name)
    name = re.sub(r'\.hdl$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\.asm$', '', name, flags=re.IGNORECASE)
    return name.lower()


def _match_files(found, expected_names, file_ext):
    matched = {}
    matches = []
    used = set()

    found_norm = {}
    for name, path in found.items():
        found_norm[_normalize(name)] = (name, path)

    # Pass 1: exact
    for exp in expected_names:
        if exp in found:
            matched[exp] = found[exp]
            used.add(exp)
            matches.append(FileMatch(exp, f"{exp}{file_ext}", "exact"))

    # Pass 2: case insensitive
    remaining = [n for n in expected_names if n not in matched]
    found_lower = {k.lower(): (k, v) for k, v in found.items()
                   if k not in used}
    for exp in remaining[:]:
        if exp.lower() in found_lower:
            orig, path = found_lower[exp.lower()]
            matched[exp] = path
            used.add(orig)
            remaining.remove(exp)
            matches.append(FileMatch(
                exp, f"{orig}{file_ext}", "case_fix",
                f"Named '{orig}{file_ext}' instead of '{exp}{file_ext}'"))

    # Pass 3: normalized
    for exp in remaining[:]:
        exp_norm = _normalize(exp)
        if exp_norm in found_norm:
            orig, path = found_norm[exp_norm]
            if orig not in used:
                matched[exp] = path
                used.add(orig)
                remaining.remove(exp)
                matches.append(FileMatch(
                    exp, f"{orig}{file_ext}", "fuzzy",
                    f"Named '{orig}{file_ext}' -- "
                    f"assumed to be '{exp}{file_ext}'"))

    # Pass 4: substring
    for exp in remaining[:]:
        exp_lower = exp.lower()
        best = None
        best_score = 0
        for name, path in found.items():
            if name in used:
                continue
            nl = name.lower()
            if exp_lower in nl or nl in exp_lower:
                score = len(exp_lower) / max(len(nl), 1)
                if score > best_score:
                    best_score = score
                    best = (name, path)
        if best and best_score > 0.4:
            orig, path = best
            matched[exp] = path
            used.add(orig)
            remaining.remove(exp)
            matches.append(FileMatch(
                exp, f"{orig}{file_ext}", "fuzzy",
                f"Named '{orig}{file_ext}' -- "
                f"assumed to be '{exp}{file_ext}'"))

    for exp in remaining:
        matches.append(FileMatch(
            exp, "", "not_found",
            f"'{exp}{file_ext}' not found in submission"))

    extra = [f"{n}{file_ext}" for n in found if n not in used]
    return matched, matches, extra


def _rename_for_sim(matched, sandbox, ext):
    for expected, source in matched.items():
        shutil.copy2(source, os.path.join(sandbox, f"{expected}{ext}"))


# ── Helpers ──────────────────────────────────────────────────

def _extract_zip(zip_path, file_ext):
    tmp = tempfile.mkdtemp(prefix="n2t_")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp)
    except zipfile.BadZipFile:
        return tmp, {}

    found = {}
    for root, dirs, files in os.walk(tmp):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
        for f in files:
            if f.startswith('.') or f.startswith('__'):
                continue
            name = f
            while name.lower().endswith(file_ext):
                name = name[:-len(file_ext)]
            if f.lower().endswith(file_ext) and name:
                if name not in found:
                    found[name] = os.path.join(root, f)
    return tmp, found


def _check_builtin(path):
    try:
        text = Path(path).read_text(encoding='utf-8', errors='ignore')
        return bool(re.search(r'\bBUILTIN\b', text, re.IGNORECASE))
    except Exception:
        return False


def _has_work(path, ext):
    try:
        text = Path(path).read_text(encoding='utf-8', errors='ignore')
        if ext == ".hdl":
            m = re.search(r'PARTS:\s*(.*?)(?:\})', text, re.DOTALL)
            if m:
                parts = re.sub(r'//.*', '', m.group(1))
                parts = re.sub(r'/\*.*?\*/', '', parts, flags=re.DOTALL)
                return len(parts.strip()) > 0
        elif ext == ".asm":
            lines = [l.strip() for l in text.splitlines()
                     if l.strip() and not l.strip().startswith('//')]
            return len(lines) > 2
        return False
    except Exception:
        return False


def _partial_credit(sandbox, chip, max_pts):
    cmp_p = os.path.join(sandbox, f"{chip}.cmp")
    out_p = os.path.join(sandbox, f"{chip}.out")
    if not os.path.exists(cmp_p) or not os.path.exists(out_p):
        return 0, 0, 0, 0, "", ""
    try:
        cmp = Path(cmp_p).read_text().splitlines()
        out = Path(out_p).read_text().splitlines()
    except Exception:
        return 0, 0, 0, 0, "", ""
    if len(cmp) < 2:
        return 0, 0, 0, 0, "", ""
    total = len(cmp) - 1
    passed = 0
    fl, fe, fa = 0, "", ""
    for i in range(1, len(cmp)):
        c = cmp[i].strip() if i < len(cmp) else ""
        o = out[i].strip() if i < len(out) else ""
        if c == o:
            passed += 1
        elif fl == 0:
            fl, fe, fa = i, c, o
    pts = round(max_pts * passed / total, 2) if total else 0
    return pts, passed, total, fl, fe, fa


def _clean_err(raw):
    lines = []
    for l in raw.split('\n'):
        l = l.strip()
        if not l or l.startswith('at ') or 'java.' in l.lower():
            continue
        if 'Exception in thread' in l:
            continue
        lines.append(l)
    return '; '.join(lines[:3])[:200] if lines else "Unknown error"


# ── Test Runner ──────────────────────────────────────────────

def _run_one(chip, matched, project):
    pts = project["chip_points"]
    mx = pts.get(chip, 1.0)
    tp = project["test_path"]
    sim = str(project["simulator_path"])
    ext = project["file_ext"]

    if chip not in matched:
        return ChipResult(chip, False, 0, mx, "missing", "Not submitted")

    if ext == ".hdl" and _check_builtin(matched[chip]):
        return ChipResult(chip, False, 0, mx, "builtin",
                          "Uses BUILTIN (not allowed)")

    work = _has_work(matched[chip], ext)
    tst = tp / f"{chip}.tst"
    cmp = tp / f"{chip}.cmp"
    if not tst.exists():
        return ChipResult(chip, False, 0, mx, "internal",
                          f"{chip}.tst not found")

    sb = tempfile.mkdtemp(prefix=f"c_{chip}_")
    try:
        _rename_for_sim(matched, sb, ext)
        shutil.copy2(tst, sb)
        if cmp.exists():
            shutil.copy2(cmp, sb)
        for x in tp.glob(f"{chip}*"):
            d = os.path.join(sb, x.name)
            if not os.path.exists(d):
                shutil.copy2(x, sb)

        r = subprocess.run(
            [sim, os.path.join(sb, f"{chip}.tst")],
            capture_output=True, text=True, timeout=60, cwd=sb)
        out = f"{r.stdout}\n{r.stderr}".strip()

        if "Comparison ended successfully" in out or \
           "End of script - Comparison ended successfully" in out:
            tt = max(0, len(cmp.read_text().splitlines()) - 1) \
                if cmp.exists() else 0
            return ChipResult(chip, True, mx, mx, "pass",
                              total_tests=tt, passed_tests=tt)

        m = re.search(r'[Cc]omparison failure at line (\d+)', out)
        if m:
            p, ps, tt, fl, fe, fa = _partial_credit(sb, chip, mx)
            return ChipResult(
                chip, False, p, mx, "mismatch",
                f"{ps}/{tt} tests passed (first fail line {fl})",
                fl, fe, fa, tt, ps)

        ce = _clean_err(out)
        if work:
            return ChipResult(chip, False, round(mx * 0.15, 2), mx,
                              "syntax", f"Syntax error (effort credit): {ce}")
        return ChipResult(chip, False, 0, mx, "syntax", ce)

    except subprocess.TimeoutExpired:
        ep = round(mx * 0.1, 2) if work else 0
        return ChipResult(chip, False, ep, mx, "timeout",
                          "Timed out (possible loop)")
    except Exception as e:
        return ChipResult(chip, False, 0, mx, "internal", str(e)[:150])
    finally:
        shutil.rmtree(sb, ignore_errors=True)


def _cascades(results, deps):
    failed = {c.name for c in results if not c.passed}
    if not failed:
        return []
    warns = []
    for c in results:
        if c.name not in failed:
            continue
        bd = [d for d in deps.get(c.name, []) if d in failed]
        if bd:
            warns.append(f"{c.name} likely fails because "
                         f"{', '.join(bd)} also broken")
    return warns


# ── Main Pipeline ────────────────────────────────────────────

async def grade_student(zip_path, student_name, user_id,
                        project_num=None, zip_filename=""):
    project = get_project(project_num)
    chips = project["chip_names"]
    pts = project["chip_points"]
    ext = project["file_ext"]
    deps = project.get("deps", {})

    tmp, raw = _extract_zip(zip_path, ext)
    try:
        result = GradingResult(
            student_name=student_name, user_id=user_id,
            project_num=project["number"],
            total_possible=project["total_points"])

        # Check zip naming
        result.zip_naming = check_zip_naming(
            zip_filename, student_name, project["number"])

        if not raw:
            result.warnings.append(f"No {ext} files found in zip")
            for c in chips:
                result.chips.append(ChipResult(
                    c, False, 0, pts[c], "missing",
                    f"No {ext} files in submission"))
                result.file_matches.append(FileMatch(
                    c, "", "not_found", f"No {ext} files in zip"))
            return result

        matched, fmatches, extra = _match_files(raw, chips, ext)
        result.file_matches = fmatches
        result.extra_files = extra

        exact = sum(1 for m in fmatches if m.match_type == "exact")
        fixed = sum(1 for m in fmatches
                    if m.match_type in ("case_fix", "fuzzy"))
        missing = sum(1 for m in fmatches if m.match_type == "not_found")
        log.info(f"  {student_name}: {exact} exact, {fixed} fixed, "
                 f"{missing} missing, {len(extra)} extra")

        if fixed > 0:
            for m in fmatches:
                if m.match_type in ("case_fix", "fuzzy"):
                    result.warnings.append(f"Naming: {m.issue}")

        loop = asyncio.get_event_loop()
        for c in chips:
            cr = await loop.run_in_executor(None, _run_one, c, matched,
                                            project)
            result.chips.append(cr)
            result.total_earned += cr.points

        result.total_earned = round(result.total_earned, 2)
        result.warnings.extend(_cascades(result.chips, deps))
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)