import os
import sqlite3
import threading
import requests
import logging
import json
import time
import subprocess
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from random import uniform, randint, choice
from datetime import datetime

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), "databases", "meds.db")

# Simulation toggle
simulate_attack = threading.Event()

# TTS uses separate process
def speak_async(text):
    subprocess.Popen([
        'python',
        os.path.join(os.path.dirname(__file__), 'speak.py'),
        text
    ])

# Doctor SMS configs
API_KEY = "e1735361-5065-49d0-849f-863ccbe135de"
DEVICE_ID = "685c0d24279700d071eeaa09"
DOCTOR_NO = "+919321830156"

def send_sms():
    resp = requests.post(
        f"https://api.textbee.dev/api/v1/gateway/devices/{DEVICE_ID}/send-sms",
        headers={'x-api-key': API_KEY},
        json={'recipients': [DOCTOR_NO], 'message': 'MediBot Alert: please consult the patient.'}
    ).json()
    return resp.get('data', {}).get('success', False)

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries(
                id INTEGER PRIMARY KEY, timestamp TEXT,
                temperature REAL, heart_rate INTEGER,
                systolic INTEGER, diastolic INTEGER, spo2 INTEGER,
                symptoms TEXT, suggested_med TEXT
            )
        """)
        conn.commit()

@app.route('/simulate', methods=['POST'])
def simulate():
    if request.json.get('on'):
        simulate_attack.set()
    else:
        simulate_attack.clear()
    return ('', 204)

def generate_vitals():
    if simulate_attack.is_set():
        return {
            "systolic": randint(160, 200),
            "diastolic": randint(100, 120),
            "heart_rate": randint(110, 140),
            "temperature": round(uniform(37.0, 38.5), 1),
            "spo2": randint(85, 93),
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "systolic": randint(100, 115),
            "diastolic": randint(65, 80),
            "heart_rate": randint(60, 90),
            "temperature": round(uniform(36.5, 37.2), 1),
            "spo2": randint(96, 99),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route('/stream')
def stream():
    def events():
        while True:
            vit = generate_vitals()
            yield f"data: {json.dumps(vit)}\n\n"
            time.sleep(2)
    return Response(stream_with_context(events()), mimetype='text/event-stream')

def suggest_med(sym, vit):
    s = sym.lower()
    alerts = []
    if vit["temperature"] > 37.2: alerts.append("High temperature")
    if vit["heart_rate"] > 100: alerts.append("High heart rate")
    if vit["systolic"] > 140 or vit["diastolic"] > 90: alerts.append("High blood pressure")
    if vit["spo2"] < 95: alerts.append("Low SpO₂")

    med = "Rest and monitor"
    if "heart attack" in s or simulate_attack.is_set():
        med = "Emergency! Call ambulance!"
    elif "cough" in s:
        med = "Cough syrup"
    elif "fever" in s:
        med = "Paracetamol"
    elif alerts and med == "Rest and monitor":
        med = "Consult a doctor"
    return med, alerts

def check_stock(med):
    return choice([True, False]), f"https://example.com/order/{med.replace(' ', '_')}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    vit = data.get('vitals', generate_vitals())
    sym = data.get('symptoms', "")
    med, alerts = suggest_med(sym, vit)
    in_stock, order_url = check_stock(med)

    if med.startswith("Consult") or med.startswith("Emergency"):
        if send_sms():
            alerts.append("Doctor SMS sent ✔️")
        else:
            alerts.append("Doctor SMS failed")

    speak_async(f"Medicine: {med}. Alerts: {'; '.join(alerts)}.")

    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT INTO entries
            (timestamp,temperature,heart_rate,systolic,diastolic,spo2,symptoms,suggested_med)
            VALUES(?,?,?,?,?,?,?,?)""", (
            datetime.utcnow().isoformat(),
            vit["temperature"], vit["heart_rate"],
            vit["systolic"], vit["diastolic"], vit["spo2"],
            sym, med
        ))
        conn.commit()

    return jsonify({
        "suggested_med": med,
        "alerts": alerts,
        "in_stock": in_stock,
        "order_url": order_url
    })

if __name__ == '__main__':
    init_db()
    app.run(debug=True, threaded=True)
