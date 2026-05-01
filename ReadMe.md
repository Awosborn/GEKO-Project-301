# GEKO Bridge UI — Quick Start

This README is focused on one goal: running the **Bridge UI** smoothly with the local project components:
- `MVP/bridge_ui` (frontend UI)
- `MVP/GEKO_PLAYABLE_MODEL` (playable bridge AI assets)
- `MVP/StreamLine` (bridge bid coach/model package)

For PR-style progress notes, see **`MVPwork/part2/PULL_REQUEST.md`**.

---

## 1) What you run

The Bridge UI is a static web app:
- `MVP/bridge_ui/index.html`
- `MVP/bridge_ui/styles.css`
- `MVP/bridge_ui/app.js`

It currently runs offline in-browser and is structured to support GEKO/StreamLine-backed decision logic.

---

## 2) Fastest way to launch Bridge UI

From repo root (`GEKO-Project-301`):

```bash
python3 -m http.server 8080
```

Then open:

```text
http://localhost:8080/MVP/bridge_ui/index.html
```

That is the most reliable local workflow because browser security restrictions can block features when opening `index.html` directly from disk.

---

## 3) Optional environment setup (for model-side work)

If you plan to work with model code (not required just to open UI), install dependencies for each module:

```bash
pip install -r MVP/GEKO_PLAYABLE_MODEL/requirements.txt
pip install -r MVP/StreamLine/requirements.txt
```

You can also review model-specific docs:
- `MVP/GEKO_PLAYABLE_MODEL/README.md`
- `MVP/StreamLine/README.md`

---

## 4) Verify Bridge UI files

Quick syntax check for the main UI script:

```bash
node --check MVP/bridge_ui/app.js
```

If this passes, your Bridge UI JavaScript is syntactically valid.

---

## 5) Troubleshooting

- **Port already in use**: run server on another port, e.g. `python3 -m http.server 9090` and use `http://localhost:9090/MVP/bridge_ui/index.html`.
- **Page opens but UI logic seems stale**: hard refresh browser cache (`Ctrl+Shift+R` / `Cmd+Shift+R`).
- **Model integration expectations**: UI is runnable standalone; deeper GEKO/StreamLine runtime binding can be layered in via backend/API wiring.

---

## 6) Documentation split (requested structure)

- **Part A (PR notes / MVP Part 2)**: `MVPwork/part2/PULL_REQUEST.md`
- **Part B (run instructions / Bridge UI)**: `ReadMe.md` (this file)
