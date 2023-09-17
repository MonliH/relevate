import pyaudio
import json
import re
import numpy as np
import time
import websocket

CHUNK = 1024

p = pyaudio.PyAudio()

info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')

HOST = 'ws://127.0.0.1:8000/audio'

s = websocket.create_connection(HOST)

out_device = None
in_device = None
for i in range(0, numdevices):
    if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        name = p.get_device_info_by_host_api_device_index(0, i).get('name')
        if "blackhole" in name.lower():
            out_device = i
        if "microphone" in name.lower():
            in_device = i

p = pyaudio.PyAudio()
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 16000
CHUNK = 4000

data = []

def callback(in_data, frame_count, time_info, status):
    # print("sent packet", frame_count)
    idx = len(data)
    data.append(in_data)

    s.send(str(idx))
    s.send_binary(in_data)
    return (in_data, pyaudio.paContinue)

def fade(audio, out=True):
    # convert to audio indices (samples)
    audio = np.frombuffer(audio, np.int16).flatten().astype(np.float32) / 32768.0

    # compute fade out curve
    # linear fade
    fade_curve = np.linspace(1.0, 0.0, len(audio)) if out else np.linspace(0.0, 1.0, len(audio))

    # apply the curve
    return (audio * fade_curve * 32768.0).astype(np.int16).tobytes()

print("starting ...")
stream = p.open(format=FORMAT, channels=CHANNELS,
                rate=SAMPLE_RATE, input=True, input_device_index=in_device,
                frames_per_buffer=CHUNK, stream_callback=callback)

out_stream = p.open(format=FORMAT, channels=CHANNELS,
                rate=SAMPLE_RATE, output=True, output_device_index=out_device,
                frames_per_buffer=CHUNK)

time.sleep(5)
import string
letters = set(string.ascii_letters)

since_last = 20
while stream.is_active():
    times = json.loads(s.recv_data()[1])
    print(times["transcript"]["text"], times["times"])
    if len(data) >= since_last:
        # ignore_times = times["times"]
        ignore_times = []
        for line in times["transcript"]["segments"]:
            for word in line["words"]:
                if re.match(r"^u+(h|m)+$", ''.join(filter(lambda x: x in letters, word["text"])), re.IGNORECASE):
                    ignore_times.append((word["start"], word["end"]))
                
                if "-" in word["text"]:
                    fragments = word["text"].split("-")
                    if len(set(len(a) for a in fragments))==1:
                        ignore_times.append((word["start"], word["end"]))
                    else:
                        num_chrs = len("".join(fragments[:-1]))
                        percent = num_chrs / (num_chrs + len(fragments[-1]))

                        ignore_times.append((word["start"], word["start"] + percent*(word["end"] - word["start"])))
        
        back_index = times["back_index"]
        print(back_index)
        together = b"".join(data[back_index-since_last+1:back_index+1])
        start = 0
        new_bytes = []
        for i, time_to_ignore in enumerate(ignore_times):
            start_of_remove, end_of_remove = [t*SAMPLE_RATE for t in time_to_ignore]
            fade_duration = 0.1*SAMPLE_RATE

            value = int(start_of_remove*2)
            offset = 0
            new_bytes.append(together[start:value])

            if len(ignore_times) > i+1 and ignore_times[i+1]:
                print(time_to_ignore, start_of_remove, end_of_remove)
                offset = int(fade_duration)
                new_bytes.append(fade(together[value:value+offset]))
                new_bytes.append(fade(together[int(end_of_remove)*2-offset:int(end_of_remove)*2], out=False))

            start = int(end_of_remove*2)
        
        new_bytes.append(together[start:])

        print(len(b"".join(new_bytes)), len(together))
        out_stream.write(b"".join(new_bytes))

stream.close()
s.close()
