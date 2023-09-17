# relevate

HTN 2023 Project.

## usage

Install [BlackHole](https://github.com/ExistentialAudio/BlackHole).

### Server

```bash
cd ai_backend
python3 -m pip install -r requirements.txt
uvicorn server:app
```

### GUI

Create `.env` and populate with `HOST="ws://localhost:8000/audio"` (or some other host).

```bash
python3 -m pip install -r requirements.txt
python3 gui.py
```
