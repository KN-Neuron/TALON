 
                    ___                                 ___
                   /   \                               /   \
              ____|  o  |_____________________________|  o  |____
             /____|_____|_____________________________|_____|____\
                    |                                   |
                    |          ┌─────────────┐          |
                    |          │   ▄▄▄▄▄▄▄   │          |
                    └──────────┤  █ ◉◉◉◉◉ █  ├──────────┘
                               │  █ ◉   ◉ █  │
                               │  █ ◉◉◉◉◉ █  │
                               │   ▀▀▀▀▀▀▀   │
                    ┌──────────┤  ╔═══════╗  ├──────────┐
                    |          │  ║ TALON ║  │          |
                    |          │  ║ ░░░░░ ║  │          |
                    |          │  ╚═══════╝  │          |
                    |          └──────┬──────┘          |
                    |               ╱ │ ╲               |
              _____|_____         ╱   │   ╲         _____|_____
             /___________\       ╱  ╔═╧═╗  ╲       /___________\
              \    |    /       ╱   ║▓▓▓║   ╲      \    |    /
                   |           ╱    ╚═╤═╝    ╲          |
                   ◉          ╱       │       ╲         ◉
                              ════════╧════════
                                   ╲  │  ╱
                                    ╲ │ ╱
                                     ╲│╱
                                      ▼
                              ░ ░ ░ ░ ░ ░ ░
                           ░ ░ ░ ░ ░ ░ ░ ░ ░ ░
                              ░ ░ ░ ░ ░ ░ ░

                    ▶ UNIT-07 ▪ AUTONOMOUS ▪ ARMED ◀

Backend streams a camera feed to a browser over WebRTC. Start these in order:

## 0. Clone

```
git lfs install
git clone <repo-url>
```

This repo uses Git LFS for `*.png` assets - run `git lfs install` once before cloning (or `git lfs pull` afterward if you already cloned without it).

## 1. Backend

```
cd apps/backend
go run ./cmd/server
```

## 2. Client (camera publisher)

```
cd apps/client
uv sync
uv run main.py
```

## 3. Frontend (viewer)

```
cd apps/frontend
npm install
npm run dev
```

Open the printed URL, pick a camera, click Connect.

Each app defaults to `http://localhost:8080` for the backend - override with `BACKEND_ADDR`, `BACKEND_URL`, or `VITE_BACKEND_URL` if needed.
