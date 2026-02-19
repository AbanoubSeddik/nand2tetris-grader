import os
import re
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
TOOLS_DIR = BASE_DIR / "tools" / "nand2tetris" / "tools"
HARDWARE_SIM = TOOLS_DIR / "HardwareSimulator.sh"
CPU_EMULATOR = TOOLS_DIR / "CPUEmulator.sh"
VM_EMULATOR = TOOLS_DIR / "VMEmulator.sh"
TEST_FILES_DIR = BASE_DIR / "grader_test_files"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "grader.db"

# ── Credentials ──────────────────────────────────────────────
MOODLE_URL = os.getenv("MOODLE_URL", "https://elearning.constructor.university")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ALLOWED_USER_IDS = [
    int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
]
DEFAULT_GROUP = os.getenv("DEFAULT_GROUP", "Group_G")

# ── Project Definitions ─────────────────────────────────────
PROJECTS = {
    1: {
        "name": "Logic Gates",
        "simulator": "HardwareSimulator",
        "file_ext": ".hdl",
        "test_dir": "project01",
        "zip_pattern": r"HW1_Gates_\w+",
        "chips": [
            ("Not",        0.65),
            ("And",        0.65),
            ("Or",         0.65),
            ("Xor",        0.65),
            ("Mux",        0.65),
            ("DMux",       0.65),
            ("Not16",      0.65),
            ("And16",      0.65),
            ("Or16",       0.65),
            ("Mux16",      0.65),
            ("Or8Way",     0.70),
            ("Mux4Way16",  0.65),
            ("Mux8Way16",  0.75),
            ("DMux4Way",   0.65),
            ("DMux8Way",   0.75),
        ],
        "deps": {
            "Not": [], "And": ["Not"], "Or": ["Not"],
            "Xor": ["Not", "And", "Or"],
            "Mux": ["Not", "And", "Or"],
            "DMux": ["Not", "And"],
            "Not16": ["Not"], "And16": ["And"], "Or16": ["Or"],
            "Mux16": ["Mux"], "Or8Way": ["Or"],
            "Mux4Way16": ["Mux16"],
            "Mux8Way16": ["Mux4Way16", "Mux16"],
            "DMux4Way": ["DMux"],
            "DMux8Way": ["DMux4Way", "DMux"],
        },
    },
    2: {
        "name": "ALU",
        "simulator": "HardwareSimulator",
        "file_ext": ".hdl",
        "test_dir": "project02",
        "zip_pattern": r"HW2_ALU_\w+",
        "chips": [
            ("HalfAdder",  0.80),
            ("FullAdder",  0.80),
            ("Add16",      0.80),
            ("Inc16",      0.80),
            ("ALU",        3.00),
            ("ALU-nostat", 3.80),
        ],
        "deps": {
            "HalfAdder": [], "FullAdder": ["HalfAdder"],
            "Add16": ["HalfAdder", "FullAdder"],
            "Inc16": ["Add16"],
            "ALU": ["Add16", "Inc16"],
            "ALU-nostat": ["Add16", "Inc16"],
        },
    },
    3: {
        "name": "Memory",
        "simulator": "HardwareSimulator",
        "file_ext": ".hdl",
        "test_dir": "project03",
        "zip_pattern": r"HW3_Memory_\w+",
        "chips": [
            ("Bit",      1.00),
            ("Register", 1.00),
            ("RAM8",     1.50),
            ("RAM64",    1.50),
            ("RAM512",   1.50),
            ("RAM4K",    1.50),
            ("RAM16K",   1.00),
            ("PC",       1.00),
        ],
        "deps": {
            "Bit": [], "Register": ["Bit"], "RAM8": ["Register"],
            "RAM64": ["RAM8"], "RAM512": ["RAM64"],
            "RAM4K": ["RAM512"], "RAM16K": ["RAM4K"],
            "PC": ["Register"],
        },
    },
    4: {
        "name": "Machine Language",
        "simulator": "CPUEmulator",
        "file_ext": ".asm",
        "test_dir": "project04",
        "zip_pattern": r"HW4_Assembly_\w+",
        "chips": [
            ("Mult", 5.00),
            ("Fill", 5.00),
        ],
        "deps": {"Mult": [], "Fill": []},
    },
    5: {
        "name": "Computer Architecture",
        "simulator": "HardwareSimulator",
        "file_ext": ".hdl",
        "test_dir": "project05",
        "zip_pattern": r"HW5_Computer_\w+",
        "chips": [
            ("Memory",   3.00),
            ("CPU",      4.00),
            ("Computer", 3.00),
        ],
        "deps": {
            "Memory": [], "CPU": [],
            "Computer": ["Memory", "CPU"],
        },
    },
}

ACTIVE_PROJECT = int(os.getenv("ACTIVE_PROJECT", "1"))

# ── Assignment detection keywords ────────────────────────────
PROJECT_KEYWORDS = {
    1: ["logic gate", "nand", "basic gate", "gates from nand",
        "not.hdl", "mux", "dmux"],
    2: ["alu", "arithmetic", "adder", "halfadder", "fulladder"],
    3: ["memory", "ram", "register", "sequential", "program counter"],
    4: ["machine language", "assembly", "mult.asm", "fill.asm"],
    5: ["computer architecture", "cpu", "computer.hdl"],
}


def get_project(project_num: int = None) -> dict:
    """Get project config with computed fields."""
    num = project_num or ACTIVE_PROJECT
    proj = PROJECTS.get(num)
    if not proj:
        raise ValueError(f"Project {num} not defined")
    proj = dict(proj)
    proj["number"] = num
    proj["chip_names"] = [c[0] for c in proj["chips"]]
    proj["chip_points"] = {c[0]: c[1] for c in proj["chips"]}
    proj["total_points"] = round(sum(c[1] for c in proj["chips"]), 2)
    proj["test_path"] = TEST_FILES_DIR / proj["test_dir"]
    sim_map = {
        "HardwareSimulator": HARDWARE_SIM,
        "CPUEmulator": CPU_EMULATOR,
        "VMEmulator": VM_EMULATOR,
    }
    proj["simulator_path"] = sim_map.get(proj["simulator"], HARDWARE_SIM)
    return proj


def detect_project(assignment_name: str) -> dict | None:
    """Auto-detect project from Moodle assignment name."""
    name_lower = assignment_name.lower()
    hw_match = re.search(r'(?:homework|hw|project)\s*#?\s*(\d+)', name_lower)
    if hw_match:
        num = int(hw_match.group(1))
        if num in PROJECTS:
            return get_project(num)
    for num, keywords in PROJECT_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return get_project(num)
    return None


_proj = get_project(ACTIVE_PROJECT)
CHIP_NAMES = _proj["chip_names"]
CHIP_POINTS = _proj["chip_points"]
TOTAL_POINTS = _proj["total_points"]
CHIP_DEPS = _proj.get("deps", {})


def validate_config():
    issues = []
    if not MOODLE_TOKEN:
        issues.append("MOODLE_TOKEN not set")
    if not TELEGRAM_TOKEN:
        issues.append("TELEGRAM_TOKEN not set")
    if not GEMINI_API_KEY:
        issues.append("GEMINI_API_KEY not set (will use template reports)")
    if not ALLOWED_USER_IDS:
        issues.append("ALLOWED_USER_IDS not set (bot open to everyone)")
    if not any(shutil.which(cmd) for cmd in ("unrar", "unar", "bsdtar")):
        issues.append("RAR extractor not found (install unrar/unar/bsdtar); "
                      ".rar submissions cannot be opened")
    proj = get_project()
    if not proj["simulator_path"].exists():
        issues.append(f"{proj['simulator']} not found")
    if not proj["test_path"].exists():
        issues.append(f"Test files not found at {proj['test_path']}")
    elif not list(proj["test_path"].glob("*.tst")):
        issues.append(f"No .tst files in {proj['test_path']}")
    return issues
