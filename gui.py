import pyaudio
import json
import re
import numpy as np
import time
import websocket

import tkinter as tk
from tkinter import ttk
from threading import Thread, Event
import dotenv
import os

dotenv.load_dotenv()

stop = Event()
in_device = None

p = pyaudio.PyAudio()
info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')

HOST = os.environ["HOST"]

devices = {}
for i in range(0, numdevices):
    if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        name = p.get_device_info_by_host_api_device_index(0, i).get('name')
        devices[name] = i

def _start_audio_module():
    p = pyaudio.PyAudio()

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
        if stop.is_set(): return (None, pyaudio.paComplete)

        idx = len(data)
        data.append(in_data)

        d = np.frombuffer(in_data, np.int16).flatten().astype(np.float32) / 32768.0
        max_d = np.mean(np.abs(d))
        pb["value"] = max_d*1000

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
        if stop.is_set(): break
        times = json.loads(s.recv_data()[1])
        
        print(times["transcript"]["text"], times["times"])
        # text_string.set(times["transcript"]["text"].strip())

        if len(data) >= since_last:
            # ignore_times = times["times"]
            ignore_times = []
            indexes = []
            idx = 0
            print(times["transcript"])
            for line in times["transcript"]["segments"]:
                for word in line["words"]:
                    idx += 1  # space
                    if re.match(r"^u+(h|m)+$", ''.join(filter(lambda x: x in letters, word["text"])), re.IGNORECASE):
                        ignore_times.append((word["start"], word["end"]))
                        indexes.append((idx, idx+len(word["text"])))
                    
                    if "-" in word["text"]:
                        fragments = word["text"].split("-")
                        if len(set(len(a) for a in fragments))==1 and fragments[0].lower() != "i":
                            ignore_times.append((word["start"], word["end"]))
                            indexes.append((idx, idx+len(word["text"])))
                        else:
                            num_chrs = len("".join(fragments[:-1]))
                            percent = num_chrs / (num_chrs + len(fragments[-1]))

                            ignore_times.append((word["start"], word["start"] + percent*(word["end"] - word["start"])))
                            indexes.append((idx, idx+len("-".join(fragments[:-1]))+1))

                    idx += len(word["text"])
            
            # write the text in times["transcript"]["text"] to the text widget, but highlight the words in indexes
            text_widget.configure(state="normal")
            text_widget.delete('1.0', tk.END)
            text_widget.insert(tk.END, times["transcript"]["text"])
            for start, end in indexes:
                text_widget.tag_add("highlight", f"1.{start}", f"1.{end}")
            text_widget.tag_config("highlight", foreground="red")
            text_widget.configure(state="disabled")

            back_index = times["back_index"]
            print(back_index)
            together = b"".join(data[back_index-since_last+1:back_index+1])
            start = 0
            new_bytes = []
            for i, time_to_ignore in enumerate(ignore_times):
                start_of_remove, end_of_remove = [t*SAMPLE_RATE for t in time_to_ignore]
                fade_duration = int(0.05*SAMPLE_RATE)

                value = int(start_of_remove*2)
                # cutoff = value
                    # cutoff -= int(fade_duration)
                if start != 0:
                    new_bytes.append(together[start:value])
                else:
                    new_bytes.append(together[start:value])

                # if len(ignore_times) > i+1 and ignore_times[i+1]:
                #     offset = int(fade_duration)
                #     new_bytes.append(fade(together[value:value+offset]))
                #     new_bytes.append(fade(together[int(end_of_remove)*2-offset:int(end_of_remove)*2], out=False))

                start = int(end_of_remove*2)
            
            new_bytes.append(together[start:])

            out_stream.write(b"".join(new_bytes))

    stream.close()
    s.close()
    out_stream.close()


def start_audio_module():
    Thread(target=_start_audio_module).start()

def toggle_button():
    if button_var.get() == "Stop":
        button.configure(style='Accent.TButton')
        button_var.set("Start")
        stop.set()
    else:
        button.configure(style='TButton')
        button_var.set("Stop")
        stop.clear()
        start_audio_module()

def dropdown_selected(event):
    selected_option = dropdown_var.get()

# Create the main window
root = tk.Tk()
root.geometry("400x300")
# do not allow window resizing
root.title("Relevate")
root.tk.call('source', 'forest-light.tcl')
ttk.Style().theme_use('forest-light')
root.resizable(False, False)


pb = ttk.Progressbar(root, orient='horizontal', mode='determinate', length=300)
pb.pack(fill='x')

# Create a StringVar to hold the button state ("On" or "Off")
button_var = tk.StringVar()
button_var.set("Start")

# Create a text label with text_string
text_widget = tk.Text(root, height=3, width=300, font=(None, 24))
text_widget.pack(pady=10)

# Create a button that toggles on and off
button = ttk.Button(root, textvariable=button_var, command=toggle_button, style='Accent.TButton')
button.pack(pady=10)

# Create a dropdown menu with some options
options = list(devices.keys())
index = [idx for idx, s in enumerate(options) if 'microphone' in s.lower()][-1]
text  = tk.Label(root, text="Select an input device:").pack(pady=5)
dropdown_var = tk.StringVar()
dropdown_var.set(options[index])  # Set the default option
dropdown = ttk.OptionMenu(root, dropdown_var, options[index], *options)
dropdown.pack()

# Bind a function to the dropdown selection
dropdown.bind("<Configure>", dropdown_selected)

# Start the Tkinter main loop
root.mainloop()
