# GEKO Bridge UI — Windows Command Prompt Quick Start

video
- https://youtu.be/xgHZAECAaWM
This guide is designed for **first-time setup on Windows** with copy/paste commands for **Command Prompt (cmd.exe)**.

---

## 1) One-time prerequisites (install these first)

Install before running commands below:
- **Git for Windows** (includes `git` command)
- **Python 3.10+** (make sure “Add Python to PATH” is checked)

Optional (only for extra checks):
- **Node.js** (for JavaScript syntax check)

---

## 2) Copy/paste setup + run commands (from scratch)

Open **Command Prompt** and paste these commands **one by one**:

```bat
git clone https://github.com/Awosborn/GEKO-Project-301.git
cd GEKO-Project-301
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r MVP\GEKO_PLAYABLE_MODEL\requirements.txt
pip install -r MVP\StreamLine\requirements.txt
python MVP\bridge_ui\server.py
```

After the last command starts the local server, open this URL in your browser:

```text
http://localhost:8000
```

---

## 3) Minimal run path (UI only)

If you only want the UI and do **not** need model dependencies yet:

```bat
git clone https://github.com/Awosborn/GEKO-Project-301.git
cd GEKO-Project-301
python MVP\bridge_ui\server.py
```

Then open:

```text
http://localhost:8000
```

---

## 4) Verify UI script syntax (optional)

If Node.js is installed:

```bat
node --check MVP\bridge_ui\app.js
```

No output usually means syntax is valid.

---

## 5) Troubleshooting

- **Deal Random Hand button appears to do nothing**:
  - Confirm you are opening the UI through the Python server (`python MVP\bridge_ui\server.py`) and not via `file:///...`.
  - Hard refresh (`Ctrl+Shift+R`) to clear cached JavaScript.
  - Open browser DevTools Console and check for JavaScript errors.

- **`py` not recognized**: use `python` instead of `py` for venv creation.
- **Port 8080 already in use**:

```bat
set PORT=9090 && python MVP\bridge_ui\server.py
```

Then use `http://localhost:9090`.

- **Changes not showing**: hard refresh browser (`Ctrl+Shift+R`).
- **Dependency install errors**: ensure Python is 3.10+ and pip is upgraded (`python -m pip install --upgrade pip`).

---

## 6) Project docs split

- PR/MVP Part 2 notes: `MVPwork/part2/PULL_REQUEST.md`
- Run instructions for Bridge UI: `ReadMe.md` (this file)
