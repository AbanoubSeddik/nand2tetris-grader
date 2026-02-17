"""
AI report generation with partial credit, naming issues, zip naming.
"""

import logging
import google.generativeai as genai
from config import GEMINI_API_KEY, get_project, ACTIVE_PROJECT
from grading_engine import GradingResult

log = logging.getLogger(__name__)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT_TEMPLATE = """\
You are a friendly TA for "Digital Systems and Computer Architecture" (CH-234) \
at Constructor University, taught by Prof. Tormasov and Dr. Ubaid.

Writing feedback for {hw_name}: {project_name}.

Rules:
- Address student by first name
- Warm, encouraging, casual-academic tone
- Perfect score: brief congrats, 2-3 sentences
- Failed/partial chips: name each, ONE sentence hint
- If partial credit given, mention tests passed
- If FILE NAMING issues exist (wrong chip filenames or wrong zip name), \
  mention them clearly but kindly and state the correct name
- If early components fail: warn about cascading dependencies
- DO NOT include numeric score (system adds it)
- NO markdown. Plain text, emoji sparingly
- Under 120 words perfect, under 250 words failures
- Sign off: "-- Your CH-234 Teaching Team"
"""

HINTS = {
    1: {
        "Not": "Not is just Nand(a, a).",
        "And": "And = Not(Nand(a, b)).",
        "Or": "De Morgan's: Or(a,b) = Nand(Not(a), Not(b)).",
        "Xor": "Xor is 1 when inputs differ.",
        "Mux": "Mux: Or(And(a,Not(sel)), And(b,sel)).",
        "DMux": "DMux: a=And(in,Not(sel)), b=And(in,sel).",
        "Not16": "Apply Not to each of the 16 bits.",
        "And16": "Apply And to each pair of the 16 bits.",
        "Or16": "Apply Or to each pair of the 16 bits.",
        "Mux16": "Apply Mux to each bit pair, sharing sel.",
        "Or8Way": "Or all 8 bits together.",
        "Mux4Way16": "Two Mux16 with sel[0], then Mux16 with sel[1].",
        "Mux8Way16": "Two Mux4Way16, then Mux16 with sel[2].",
        "DMux4Way": "DMux by sel[1], then each half by sel[0].",
        "DMux8Way": "DMux by sel[2], then DMux4Way on each half.",
    },
    2: {
        "HalfAdder": "sum=Xor(a,b), carry=And(a,b).",
        "FullAdder": "Two HalfAdders chained, Or the carries.",
        "Add16": "Chain 16 FullAdders.",
        "Inc16": "Add16(in, 1).",
        "ALU": "Zero/negate inputs, add or and, negate output.",
        "ALU-nostat": "Same as ALU without zr and ng.",
    },
    3: {
        "Bit": "Mux feeding into a DFF.",
        "Register": "16 Bit chips in parallel.",
        "RAM8": "DMux8Way load, 8 Registers, Mux8Way16 outputs.",
        "RAM64": "8 RAM8 chips.", "RAM512": "8 RAM64 chips.",
        "RAM4K": "8 RAM512 chips.", "RAM16K": "4 RAM4K chips.",
        "PC": "If reset out=0, elif load out=in, elif inc out++.",
    },
    4: {
        "Mult": "Loop: add R0 to result R1 times. Store in R2.",
        "Fill": "Read KBD. Nonzero: fill -1. Zero: fill 0. Loop.",
    },
    5: {
        "Memory": "RAM16K + Screen + Keyboard via address bits.",
        "CPU": "A-inst: load A. C-inst: ALU + jumps.",
        "Computer": "Wire CPU + Memory + ROM32K.",
    },
}


async def generate_report(result: GradingResult) -> str:
    project = get_project(result.project_num)
    hw = f"Homework {result.project_num}"
    pname = project["name"]

    chip_lines = []
    errors = []
    for c in result.chips:
        if c.passed:
            chip_lines.append(f"  PASS  {c.name} ({c.points}/{c.max_points})")
        elif c.points > 0:
            chip_lines.append(
                f"  PARTIAL  {c.name} -- {c.passed_tests}/{c.total_tests} "
                f"tests, {c.points}/{c.max_points} pts")
            d = f"{c.name}: {c.error_msg}"
            if c.expected and c.actual:
                d += f"\n    Expected: {c.expected}\n    Got:      {c.actual}"
            errors.append(d)
        else:
            chip_lines.append(
                f"  FAIL  {c.name} -- {c.error_type}: {c.error_msg}")
            d = f"{c.name} ({c.error_type}): {c.error_msg}"
            if c.expected and c.actual:
                d += f"\n    Expected: {c.expected}\n    Got:      {c.actual}"
            errors.append(d)

    naming = ""
    if result.has_naming_issues:
        nl = ["File naming issues:"]
        if result.zip_naming and not result.zip_naming.is_correct:
            nl.append(f"  - ZIP: {result.zip_naming.issue}")
        for m in result.naming_issues:
            nl.append(f"  - {m.issue}")
        naming = "\n" + "\n".join(nl)

    cascade_w = [w for w in result.warnings if not w.startswith("Naming:")]
    cascade = ""
    if cascade_w:
        cascade = "\nCascade warnings:\n" + \
            "\n".join(f"  - {w}" for w in cascade_w)

    prompt = (
        f"Student: {result.student_name}\n"
        f"Score: {result.total_earned}/{result.total_possible} "
        f"({result.percentage}%)\n\n"
        f"Results:\n{chr(10).join(chip_lines)}\n\n"
        f"Errors:\n{chr(10).join(errors) if errors else 'All passed!'}\n"
        f"{naming}\n{cascade}")

    system = SYSTEM_PROMPT_TEMPLATE.format(hw_name=hw, project_name=pname)

    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            resp = await model.generate_content_async(
                contents=f"{system}\n\n---\n\n{prompt}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7, max_output_tokens=500))
            text = resp.text.strip()
            if text and len(text) > 30:
                return text
        except Exception as e:
            log.warning(f"Gemini failed: {e}")

    return _template(result)


def _template(result):
    project = get_project(result.project_num)
    hints = HINTS.get(result.project_num, {})
    ext = project["file_ext"]
    first = result.student_name.split()[0] if result.student_name else "there"

    lines = [f"Hi {first},\n"]
    lines.append(f"Here's your feedback for HW{result.project_num} -- "
                 f"{project['name']}:\n")

    # Zip naming
    if result.zip_naming and not result.zip_naming.is_correct:
        lines.append(f"NOTE on zip naming: {result.zip_naming.issue}\n")

    # File naming
    fixable = [m for m in result.naming_issues
                if m.match_type != "not_found"]
    if fixable:
        lines.append("NOTE on file naming:")
        for m in fixable:
            lines.append(f"  {m.issue}")
        lines.append("  Please use exact filenames next time "
                      "(case-sensitive).\n")

    if result.percentage == 100 and not result.has_naming_issues:
        lines.append("Perfect score! All tests pass. Excellent work.\n")
    elif result.percentage == 100:
        lines.append("All tests pass! Just fix the naming next time.\n")
    else:
        passed = result.passed_names
        failed = result.failed
        partial = [c for c in failed if c.points > 0]
        zero = [c for c in failed if c.points == 0]

        if passed:
            lines.append(f"Passing ({len(passed)}/{len(result.chips)}): "
                         f"{', '.join(passed)}\n")

        if partial:
            lines.append("Partial credit:")
            for c in partial:
                h = hints.get(c.name, "")
                if c.error_type == "mismatch" and c.passed_tests > 0:
                    lines.append(
                        f"  {c.name}: {c.passed_tests}/{c.total_tests} "
                        f"tests ({c.points}/{c.max_points} pts)")
                else:
                    lines.append(
                        f"  {c.name}: effort credit "
                        f"({c.points}/{c.max_points} pts)")
                if h:
                    lines.append(f"    Hint: {h}")
            lines.append("")

        if zero:
            lines.append("Needs work:")
            for c in zero:
                h = hints.get(c.name, "")
                if c.error_type == "missing":
                    lines.append(f"  {c.name}: Not found in your zip.")
                elif c.error_type == "mismatch":
                    lines.append(f"  {c.name}: All tests failed.")
                elif c.error_type == "builtin":
                    lines.append(f"  {c.name}: Uses BUILTIN -- "
                                 "implement yourself.")
                elif c.error_type == "syntax":
                    lines.append(f"  {c.name}: Syntax error -- "
                                 f"{c.error_msg[:60]}")
                elif c.error_type == "timeout":
                    lines.append(f"  {c.name}: Timed out.")
                if h:
                    lines.append(f"    Hint: {h}")

        cascade = [w for w in result.warnings
                   if not w.startswith("Naming:")]
        if cascade:
            lines.append("")
            for w in cascade:
                lines.append(f"  Note: {w}")
        lines.append("\nFix earlier components first.\n")

    if result.extra_files:
        lines.append(f"Extra files (not needed): "
                     f"{', '.join(result.extra_files)}\n")

    lines.append("Questions? Don't hesitate to ask!\n")
    lines.append("-- Your CH-234 Teaching Team")
    return '\n'.join(lines)


def format_header(result):
    pct = result.percentage
    np = len(result.passed_names)
    npar = len([c for c in result.chips if not c.passed and c.points > 0])
    nt = len(result.chips)

    if pct == 100: emoji = "🌟"
    elif pct >= 80: emoji = "✅"
    elif pct >= 50: emoji = "⚠️"
    else: emoji = "❌"

    parts = [f"{np} pass"]
    if npar: parts.append(f"{npar} partial")
    nf = nt - np - npar
    if nf: parts.append(f"{nf} fail")

    nflag = " ⚠️naming" if result.has_naming_issues else ""

    return (f"{emoji} {result.student_name}\n"
            f"Score: {result.total_earned}/{result.total_possible} "
            f"({pct}%) -- {', '.join(parts)}{nflag}")