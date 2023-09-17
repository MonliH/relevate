import asyncio
import speech
from collections import deque

from fastapi import FastAPI
from fastapi import WebSocket, WebSocketDisconnect
import multiprocessing as mp
import websockets
import numpy as np
import json
from queue import Empty

from concurrent.futures import ProcessPoolExecutor

app = FastAPI()
pool = ProcessPoolExecutor()

class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(MyEncoder, self).default(obj)

def transcribe(arg):
    transcript = speech.transcribe_audio(arg)
    times = []
    try:
        model_output = speech.get_tokens(transcript["text"])
        # times = speech.get_times_to_cut(transcript, model_output)
    except:
        model_output = None
    output = {"transcript": transcript, "model": model_output, "times": times}
    return output

@app.websocket("/audio")
async def audio(ws: WebSocket):
    m = mp.Manager()
    q = m.Queue()

    await ws.accept()
    CHUNK_SIZE = 20
    chunks = deque()
    last_query = 0
    try:
        while True:
            index = int(await ws.receive_text())
            data = await ws.receive_bytes()
            chunks.append(data)
            if len(chunks) > CHUNK_SIZE:
                chunks.popleft()
            
            if last_query >= CHUNK_SIZE:
                last_query = 0
                print(len(b''.join(chunks)))
                audio = chunks_to_nparray(b''.join(chunks))
                res = transcribe(audio)
                res["back_index"] = index
                await ws.send_text(json.dumps(res, cls=MyEncoder))

            last_query += 1
    except WebSocketDisconnect:
        return

def chunks_to_nparray(chunks):
    return np.frombuffer(chunks, np.int16).flatten().astype(np.float32) / 32768.0
