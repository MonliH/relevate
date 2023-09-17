import whisper_timestamped as whisper
import time
import re
from transformers import pipeline, AutoModelForTokenClassification, AutoTokenizer

red = "\u001b[31m"
reset = "\u001b[0m"

model = whisper.load_model("medium", device="cuda:0")

model_name = "bert-finetuned/"
token_class_model = AutoModelForTokenClassification.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

def transcribe_audio(audio):
    prompt = "uhm I st-st stammer a lot like uhm yeah but uh like I-I I doing it r-r-r really badly. "
    result = whisper.transcribe_timestamped(model, audio, language="en", initial_prompt=prompt,
                                            no_speech_threshold=0.6, logprob_threshold=-0.5, condition_on_previous_text=False)

    return result

def get_tokens(text):
    pipe = pipeline("token-classification", model=token_class_model, tokenizer=tokenizer)
    res = pipe(text.replace("-", " ").lower())

    return res

import string
printable = set(string.ascii_letters)
def ascii(s):
    return ''.join(filter(lambda x: x in printable, s))

def get_times_to_cut(transcript, model_output):
    times_to_cut = []
    words = []
    for segment in transcript["segments"]:
        words.extend(segment["words"])

    while words:
        next_word = words.pop(0)
        matched_pred = ""
        is_filtered_out = []
        while ascii(next_word["text"].lower().strip()) != ascii(matched_pred.lower().strip()):
            matched_res = model_output.pop(0)
            matched_pred += matched_res["word"].strip().replace("Ġ", "")
            is_filtered_out.append(matched_res["entity"] == "bad")

        if all(is_filtered_out):
            times_to_cut.append((next_word["start"], next_word["end"]))

    return times_to_cut

if __name__ == "__main__":
    start = time.time()
    audio = whisper.load_audio("New Recording 18.m4a")
    transcript = transcribe_audio(audio)
    model_output = get_tokens(transcript["text"])
    print(get_times_to_cut(transcript, model_output), time.time()-start)
