# speak.py
import sys
import pyttsx3

if len(sys.argv) > 1:
    text = sys.argv[1]
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[0].id)
    engine.say(text)
    engine.runAndWait()
