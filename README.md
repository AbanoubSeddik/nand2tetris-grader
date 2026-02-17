## `README.md`

# nand2tetris Auto-Grader Bot

Automated grading system for **Digital Systems & Computer Architecture (CH-234)**
at Constructor University. Fetches submissions from Moodle, grades them using the
official nand2tetris simulators, generates AI-powered feedback reports, and submits
grades back to Moodle — all from Telegram.

## Features

- **Moodle Integration** — fetches submissions, submits grades + feedback automatically
- **Group Filtering** — grade only your assigned group (Group_A through Group_J)
- **Auto-Detection** — detects which homework from the assignment name
- **Partial Credit** — compares test output line-by-line, awards proportional points
- **Effort Credit** — 15% credit for files with syntax errors but real student work
- **Fuzzy File Matching** — handles wrong case, spaces, duplicates in filenames
- **Zip Naming Check** — reports incorrect zip naming in feedback
- **AI Reports** — Google Gemini generates personalized, human-tone feedback
- **Template Fallback** — works without Gemini (template-based reports)
- **Cascade Detection** — warns when failures are caused by broken dependencies
- **Review Flow** — review each grade in Telegram before submitting to Moodle
- **Projects 1–5** — Logic Gates, ALU, Memory, Machine Language, Computer Architecture

## How It Works

```
/grade → Pick Course → Pick Assignment
    ↓
Auto-detects: HW1 (Logic Gates), HW2 (ALU), etc.
    ↓
Shows your default group (e.g., Group_G)
    ↓
Downloads all ungraded zips from Moodle
    ↓
Fuzzy-matches filenames to expected chip names
    ↓
Runs HardwareSimulator/CPUEmulator on each component
    ↓
Calculates score with partial credit
    ↓
AI generates personalized feedback (including naming issues)
    ↓
Shows you each student: [✅ Submit] [✏️ Edit] [⏭ Skip]
    ↓
Submits grade + feedback to Moodle
```

## Quick Start (5 minutes)

### Prerequisites

- Docker (recommended) or Python 3.12+ with Java 21+
- A Moodle account with TA access to CH-234
- Telegram account

### Step 1: Clone

```bash
git clone https://github.com/YOUR_USERNAME/nand2tetris-grader.git
cd nand2tetris-grader
```

### Step 2: Get Your API Keys

You need **3 tokens**. Never share these with anyone.

#### Moodle Token

1. Log into https://elearning.constructor.university
2. Go to **Profile → Preferences → Security Keys**
   - Direct: https://elearning.constructor.university/user/managetoken.php
3. If you have an existing `Moodle mobile web service` token, click **Reset**
4. Copy the new token value immediately

#### Telegram Bot Token

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Choose a name and username
4. Copy the token

#### Gemini API Key (free)

1. Go to https://aistudio.google.com/apikey
2. Sign in with Google
3. Create API Key, copy it

#### Your Telegram User ID

1. Open Telegram, message `@userinfobot`
2. It replies with your numeric ID (e.g., `123456789`)

### Step 3: Configure

```bash
cp .env.example .env
nano .env
```

Fill in your values:

```env
MOODLE_URL=https://elearning.constructor.university
MOODLE_TOKEN=your_moodle_token_here
TELEGRAM_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
ALLOWED_USER_IDS=your_telegram_user_id_here
DEFAULT_GROUP=Group_G
```

**Multiple TAs?** Comma-separate the user IDs:

```env
ALLOWED_USER_IDS=123456789,987654321,555555555
```

**Your group?** Change `DEFAULT_GROUP`:

```env
DEFAULT_GROUP=Group_A
```

### Step 4: Download nand2tetris Tools

1. Go to https://www.nand2tetris.org/software
2. Download the Nand2tetris Software Suite
3. Extract and copy:

```bash
unzip ~/Downloads/nand2tetris.zip -d /tmp/n2t
mkdir -p tools/nand2tetris
cp -r /tmp/n2t/nand2tetris/tools tools/nand2tetris/
chmod +x tools/nand2tetris/tools/*.sh
```

### Step 5: Copy Test Files

```bash
# Project 1: Logic Gates
mkdir -p grader_test_files/project01
cp /tmp/n2t/nand2tetris/projects/1/*.tst grader_test_files/project01/
cp /tmp/n2t/nand2tetris/projects/1/*.cmp grader_test_files/project01/

# Project 2: ALU
mkdir -p grader_test_files/project02
cp /tmp/n2t/nand2tetris/projects/2/*.tst grader_test_files/project02/
cp /tmp/n2t/nand2tetris/projects/2/*.cmp grader_test_files/project02/

# Project 3: Memory
mkdir -p grader_test_files/project03
cp /tmp/n2t/nand2tetris/projects/3/a/*.tst grader_test_files/project03/
cp /tmp/n2t/nand2tetris/projects/3/a/*.cmp grader_test_files/project03/
cp /tmp/n2t/nand2tetris/projects/3/b/*.tst grader_test_files/project03/
cp /tmp/n2t/nand2tetris/projects/3/b/*.cmp grader_test_files/project03/

# Project 4: Machine Language
mkdir -p grader_test_files/project04
cp /tmp/n2t/nand2tetris/projects/4/mult/*.tst grader_test_files/project04/
cp /tmp/n2t/nand2tetris/projects/4/mult/*.cmp grader_test_files/project04/
cp /tmp/n2t/nand2tetris/projects/4/fill/*.tst grader_test_files/project04/
cp /tmp/n2t/nand2tetris/projects/4/fill/*.cmp grader_test_files/project04/

# Project 5: Computer Architecture
mkdir -p grader_test_files/project05
cp /tmp/n2t/nand2tetris/projects/5/*.tst grader_test_files/project05/
cp /tmp/n2t/nand2tetris/projects/5/*.cmp grader_test_files/project05/
```

### Step 6: Run

```bash
docker compose up --build
```

You should see:

```
n2t-grader  |   Default group: Group_G
n2t-grader  |   Active project: 1
n2t-grader  | 🤖 Bot starting... Press Ctrl+C to stop.
```

### Step 7: Test

Open Telegram → find your bot → send:

- `/test` — verify Moodle connection
- `/grade` — start grading

## Telegram Commands

| Command   | Description                    |
|-----------|--------------------------------|
| `/grade`  | Start grading an assignment    |
| `/test`   | Test Moodle connection         |
| `/status` | Current grading session status |
| `/cancel` | Cancel current grading flow    |

## Grading System

### How Scores Are Calculated

| Situation | Credit |
|-----------|--------|
| All tests pass | Full points |
| Some tests pass | Proportional (e.g., 3/4 tests = 75% of points) |
| Syntax error but student wrote code | 15% effort credit |
| Timeout but student wrote code | 10% effort credit |
| Uses BUILTIN keyword | 0 (flagged) |
| File missing | 0 |

### File Name Handling

| Student Submits | Grader Does | Report Says |
|----------------|-------------|-------------|
| `Not.hdl` | Exact match | (nothing) |
| `not.hdl` | Renames to `Not.hdl` | "Named 'not.hdl' instead of 'Not.hdl'" |
| `AND.hdl` | Renames to `And.hdl` | "Named 'AND.hdl' instead of 'And.hdl'" |
| `Or gate.hdl` | Fuzzy match → `Or.hdl` | "Named 'Or gate.hdl' — assumed to be 'Or.hdl'" |
| `And (1).hdl` | Strips `(1)` → `And.hdl` | Reports naming issue |
| `Not.hdl.hdl` | Strips double ext | Reports naming issue |
| (missing) | 0 points | "Not found in submission" |

### Zip Name Checking

Expected: `HW1_Gates_FirstName_LastName.zip`

If a student submits `homework1.zip` or `gates.zip`, the report will note:
> "Zip named 'homework1.zip' — should be 'HW1_Gates_Sarah_Cohen.zip'"

## Supported Projects

### Project 1: Logic Gates (10 pts)

| Chip | Points | Chip | Points |
|------|--------|------|--------|
| Not | 0.65 | Not16 | 0.65 |
| And | 0.65 | And16 | 0.65 |
| Or | 0.65 | Or16 | 0.65 |
| Xor | 0.65 | Mux16 | 0.65 |
| Mux | 0.65 | Or8Way | 0.70 |
| DMux | 0.65 | Mux4Way16 | 0.65 |
| | | Mux8Way16 | 0.75 |
| | | DMux4Way | 0.65 |
| | | DMux8Way | 0.75 |

### Project 2: ALU (10 pts)

| Chip | Points |
|------|--------|
| HalfAdder | 0.80 |
| FullAdder | 0.80 |
| Add16 | 0.80 |
| Inc16 | 0.80 |
| ALU | 3.00 |
| ALU-nostat | 3.80 |

### Project 3: Memory (10 pts)

| Chip | Points |
|------|--------|
| Bit | 1.00 |
| Register | 1.00 |
| RAM8 | 1.50 |
| RAM64 | 1.50 |
| RAM512 | 1.50 |
| RAM4K | 1.50 |
| RAM16K | 1.00 |
| PC | 1.00 |

### Project 4: Machine Language (10 pts)

| Program | Points |
|---------|--------|
| Mult | 5.00 |
| Fill | 5.00 |

### Project 5: Computer Architecture (10 pts)

| Chip | Points |
|------|--------|
| Memory | 3.00 |
| CPU | 4.00 |
| Computer | 3.00 |

### Projects 6–12: Not Yet Supported

These projects require running student code (Python/Java), which needs
sandboxed execution. See "Adding New Projects" below.

## Changing Point Values

Edit `config.py` → `PROJECTS` dictionary:

```python
1: {
    "chips": [
        ("Not", 0.65),    # change points here
        ("And", 0.65),
        ...
    ],
}
```

## Project Structure

```
nand2tetris-grader/
├── .env                      # YOUR credentials (never commit!)
├── .env.example              # template for other TAs
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── bot.py                    # Telegram bot (main entry)
├── config.py                 # Project configs + grading schemes
├── moodle_client.py          # Moodle REST API client
├── grading_engine.py         # Zip extraction + simulator + partial credit
├── ai_report.py              # Gemini report generation
├── database.py               # SQLite state tracking
├── grader_test_files/        # Official .tst/.cmp files
│   ├── project01/
│   ├── project02/
│   ├── project03/
│   ├── project04/
│   └── project05/
├── tools/                    # nand2tetris simulators
│   └── nand2tetris/tools/
└── data/                     # SQLite DB (auto-created)
    └── grader.db
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot says "Not authorized" | Get ID from `@userinfobot`, add to `ALLOWED_USER_IDS` |
| Moodle connection fails | Token expired → reset at Security Keys page |
| "HardwareSimulator not found" | Check `tools/nand2tetris/tools/HardwareSimulator.sh` |
| "No .tst files" | Copy test files to `grader_test_files/projectXX/` |
| Group not found | Check exact name (case-sensitive) |
| Gemini fails | Falls back to templates automatically |
| Container exits | Run `docker compose logs` |
| Java errors | `docker compose exec bot java -version` |
| Wrong project detected | Set `ACTIVE_PROJECT=N` in `.env` as fallback |

## For New TAs — Quick Checklist

1. Clone this repo
2. `cp .env.example .env`
3. Fill in YOUR tokens (Moodle, Telegram, Gemini)
4. Change `DEFAULT_GROUP` to your assigned group
5. Change `ALLOWED_USER_IDS` to your Telegram ID
6. `docker compose up --build`
7. Message your bot `/test` then `/grade`

## Security

- **Never commit `.env`** — it's in `.gitignore`
- **Never share tokens** in chat, email, or anywhere
- If a token is leaked, revoke immediately:
  - Moodle: Security Keys → Reset
  - Telegram: @BotFather → /revoke
  - Gemini: aistudio.google.com → Delete + recreate
- Bot only accepts commands from `ALLOWED_USER_IDS`

## Common Operations

### Rebuild after code changes

```bash
docker compose up --build
```

### Run in background

```bash
docker compose up -d
docker compose logs -f     # watch logs
```

### Stop

```bash
docker compose down
```

### Shell into container

```bash
docker compose exec bot bash
```

### Check database

```bash
docker compose exec bot python3 -c "
import asyncio, database as db
async def check():
    await db.init_db()
    s = await db.get_session_summary(1)
    print(s)
asyncio.run(check())
"
```

## License

Internal tool for CH-234 Digital Systems and Computer Architecture TAs at Constructor University.
