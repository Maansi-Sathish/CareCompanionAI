import os
import sys
import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI, Form, File, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker



# -----------------------------------------------------------------------------
# HARDWARE AUDIO BUZZER DRIVERS (5-BEEP SEQUENCER)
# -----------------------------------------------------------------------------
try:
    if sys.platform == "win32":
        import winsound
    else:
        winsound = None
except ImportError:
    winsound = None

def trigger_hardware_beep(frequency: int, duration: int, count: int = 5):
    """Triggers a motherboard buzzer sequence for exactly 'count' times with intervals."""
    for _ in range(count):
        if winsound:
            try:
                winsound.Beep(frequency, duration)
            except Exception:
                print("\a", end="", flush=True)  # Terminal bell fallback
        else:
            print("\a", end="", flush=True)  # Fallback terminal bell
        import time
        time.sleep(0.12)  # Space gap between beeps so they stay distinct

# -----------------------------------------------------------------------------
# DATABASE STORAGE ARCHITECTURE
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///carecompanion.db")
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Medicine(Base):
    __tablename__ = "medicines"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    dosage = Column(String)
    scheduled_time = Column(String)
    frequency_type = Column(String)  # "daily" or "custom"
    selected_days = Column(String, default="All")  # Comma-separated weekdays e.g. "Monday,Wednesday"
    is_taken_today = Column(Boolean, default=False)

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    doctor_name = Column(String)
    specialty = Column(String)
    date_time = Column(String)
    hospital = Column(String)
    prescription_path = Column(String, nullable=True)
    morning_alert_sent = Column(Boolean, default=False)   # "Doctor appointment today" alert
    reminder_alert_sent = Column(Boolean, default=False)  # 30-minutes-before alert

class CaregiverProfile(Base):
    __tablename__ = "caregiver_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Not Configured")
    phone = Column(String, default="None")
    email = Column(String, default="None")

class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    medicine_name = Column(String)
    recipient = Column(String)
    status = Column(String)
    event_type = Column(String)  # "SUCCESS" or "MISSED ESCALATION"

Base.metadata.create_all(bind=engine)

# Initialize caregiver profile layer baseline row
db_init = SessionLocal()
if db_init.query(CaregiverProfile).count() == 0:
    db_init.add(CaregiverProfile(name="Primary Caregiver", phone="Not Added", email="Not Added"))
    db_init.commit()
db_init.close()

# -----------------------------------------------------------------------------
# ASYNCHRONOUS INTELLIGENT WORKER AGENTS
# -----------------------------------------------------------------------------
app = FastAPI(title="CareCompanionAI Multi-Page App Engine")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

async def background_monitoring_agent():
    while True:
        db = SessionLocal()
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            current_date_str = now.strftime("%Y-%m-%d")
            current_weekday = now.strftime("%A")  # Get full day name (e.g., "Monday")
            
            caregivers = db.query(CaregiverProfile).all()
            if caregivers:
                recipient_label = ", ".join(f"{c.name} ({c.phone})" for c in caregivers)
            else:
                recipient_label = "No caregivers configured"

            # 1. Active Medication Compliance Tracker Loop
            medicines = db.query(Medicine).all()
            for med in medicines:
                # Determine if the medicine is scheduled for today
                is_due_today = False
                if med.frequency_type == "daily":
                    is_due_today = True
                elif med.frequency_type == "custom" and med.selected_days:
                    days_list = [d.strip() for d in med.selected_days.split(",")]
                    if current_weekday in days_list:
                        is_due_today = True

                if is_due_today:
                    # Trigger exactly 5 sharp beeps at the exact scheduled target window
                    if med.scheduled_time == current_time_str and not med.is_taken_today:
                        print(f"[⏰ ALARM TARGET] {med.name} due now. Executing 5 hardware tones.")
                        trigger_hardware_beep(frequency=1000, duration=400, count=5)
                        db.add(NotificationLog(
                            medicine_name=med.name,
                            recipient=recipient_label,
                            status=f"DUE NOW: Time to take {med.name} ({med.dosage})",
                            event_type="MEDICINE_DUE"
                        ))
                        db.commit()

                    # 10-Minute Grace Window Violation Ceiling Trigger (5 high beeps)
                    try:
                        med_time = datetime.strptime(med.scheduled_time, "%H:%M")
                        target_alert_time = (med_time + timedelta(minutes=10)).strftime("%H:%M")
                        
                        if current_time_str == target_alert_time and not med.is_taken_today:
                            existing_log = db.query(NotificationLog).filter(
                                NotificationLog.medicine_name == med.name,
                                NotificationLog.event_type == "MISSED ESCALATION",
                                NotificationLog.timestamp.like(f"{current_date_str} {current_time_str[:-1]}%")
                            ).first()
                            
                            if not existing_log:
                                print(f"[⚠️ ESCALATION] 10-min grace expired for {med.name}. Dispatching alert to caregiver.")
                                trigger_hardware_beep(frequency=2100, duration=500, count=5)
                                
                                new_log = NotificationLog(
                                    medicine_name=med.name,
                                    recipient=recipient_label,
                                    status="ALERT: Medication missed past 10-minute safe threshold!",
                                    event_type="MISSED ESCALATION"
                                )
                                db.add(new_log)
                                db.commit()
                    except Exception as e:
                        print(f"[ERROR AGENT] Delta processing error: {e}")

            # 2. Appointment Radar Warnings
            appointments = db.query(Appointment).all()
            for appt in appointments:
                try:
                    appt_dt = datetime.strptime(appt.date_time, "%Y-%m-%d %H:%M")

                    # 2a. Morning-of alert: "Doctor appointment today" (fires once, any time
                    # from midnight onward on the appointment's date, so a brief server restart
                    # can't cause it to be skipped entirely)
                    if (
                        appt_dt.strftime("%Y-%m-%d") == current_date_str
                        and not appt.morning_alert_sent
                        and now <= appt_dt
                    ):
                        print(f"[📅 TODAY] Doctor appointment today with Dr. {appt.doctor_name} ({appt.specialty}).")
                        trigger_hardware_beep(frequency=800, duration=350, count=3)
                        db.add(NotificationLog(
                            medicine_name=f"Appointment: Dr. {appt.doctor_name}",
                            recipient=recipient_label,
                            status="REMINDER: Doctor appointment today!",
                            event_type="APPT_MORNING"
                        ))
                        appt.morning_alert_sent = True
                        db.commit()

                    # 2b. 30-minutes-before alert (fires once, from the 30-min mark onward,
                    # so it isn't missed if the exact minute is skipped by a restart)
                    alert_window = appt_dt - timedelta(minutes=30)
                    if (
                        not appt.reminder_alert_sent
                        and alert_window <= now < appt_dt
                    ):
                        print(f"[🚨 RADAR] Appointment proximity alert! 30 mins remaining.")
                        trigger_hardware_beep(frequency=600, duration=300, count=3)
                        db.add(NotificationLog(
                            medicine_name=f"Appointment: Dr. {appt.doctor_name}",
                            recipient=recipient_label,
                            status="REMINDER: Appointment in 30 minutes!",
                            event_type="APPT_30MIN"
                        ))
                        appt.reminder_alert_sent = True
                        db.commit()
                except Exception as e:
                    print(f"[ERROR AGENT] Appointment processing error: {e}")

            # 3. Midnight Routine Compliance Resets
            if now.strftime("%H:%M:%S") == "00:00:00":
                db.query(Medicine).update({Medicine.is_taken_today: False})
                db.commit()

        except Exception as e:
            print(f"[CRITICAL WORKER EXCEPTION] Background agent issue: {e}")
        finally:
            db.close()
        
        await asyncio.sleep(60)

@app.on_event("startup")
async def start_background_workers():
    asyncio.create_task(background_monitoring_agent())

# -----------------------------------------------------------------------------
# GLOBAL EMBEDDED NAVIGATION WRAPPER COMPONENT
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# BROWSER-SIDE ALERTS (real audio + pop-ups, since a cloud server has no
# speaker of its own — this plays sound and shows notifications on whichever
# device actually has the site open)
# -----------------------------------------------------------------------------
ALERTS_SCRIPT = """
<div id="ccai-toast-container" style="position:fixed; top:16px; right:16px; z-index:9999; display:flex; flex-direction:column; gap:10px; max-width:320px;"></div>
<script>
(function() {
    const STORAGE_KEY = 'ccai_last_log_id';
    let audioCtx = null;

    function playBeep(freq, count) {
        try {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            // Defensive resume: if the context ever ends up suspended (e.g. the
            // tab was backgrounded, or the browser auto-suspended it), nudge it
            // back awake before scheduling tones. This does NOT establish the
            // initial user-gesture unlock by itself -- see the click handler
            // below for that -- but it keeps things reliable afterwards.
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
            let t = audioCtx.currentTime;
            for (let i = 0; i < count; i++) {
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq;
                gain.gain.value = 0.2;
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start(t);
                osc.stop(t + 0.35);
                t += 0.5;
            }
        } catch (e) { console.error('Beep failed:', e); }
    }

    function showToast(title, body) {
        const container = document.getElementById('ccai-toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.style.cssText = "background:#0f172a; border:1px solid rgba(99,102,241,0.4); border-radius:14px; padding:14px 16px; box-shadow:0 20px 40px rgba(0,0,0,0.4); animation: ccaiSlideIn 0.25s ease-out;";
        toast.innerHTML = "<p style='font-size:12px; font-weight:800; color:#a5b4fc; margin:0;'>" + title + "</p><p style='font-size:12px; color:#cbd5e1; margin:4px 0 0 0;'>" + body + "</p>";
        container.appendChild(toast);
        setTimeout(function() { toast.remove(); }, 15000);
    }

    function notifyBrowser(title, body) {
        if (window.Notification && Notification.permission === 'granted') {
            try { new Notification(title, { body: body }); } catch (e) {}
        }
    }

    function handleEvent(log) {
        var title, freq, count;
        if (log.event_type === 'MEDICINE_DUE') { title = '⏰ Medicine Due'; freq = 1000; count = 5; }
        else if (log.event_type === 'MISSED ESCALATION') { title = '⚠️ Missed Dose Alert'; freq = 2100; count = 5; }
        else if (log.event_type === 'APPT_MORNING') { title = '📅 Appointment Today'; freq = 800; count = 3; }
        else if (log.event_type === 'APPT_30MIN') { title = '🚨 Appointment Soon'; freq = 600; count = 3; }
        else { return; }
        showToast(title, log.status);
        notifyBrowser(title, log.status);
        playBeep(freq, count);
    }

    async function pollLogs() {
        try {
            const res = await fetch('/api/raw/logs');
            if (!res.ok) return;
            const logs = await res.json();
            if (!logs.length) return;
            const lastSeen = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10);
            const newOnes = logs.filter(function(l) { return l.id > lastSeen; }).sort(function(a, b) { return a.id - b.id; });
            newOnes.forEach(handleEvent);
            const maxId = Math.max.apply(null, logs.map(function(l) { return l.id; }));
            localStorage.setItem(STORAGE_KEY, maxId);
        } catch (e) { console.error(e); }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // On the very first visit ever, seed the "last seen" id so old history
        // doesn't all fire as pop-ups at once.
        if (!localStorage.getItem(STORAGE_KEY)) {
            fetch('/api/raw/logs').then(function(r) { return r.json(); }).then(function(logs) {
                const maxId = logs.length ? Math.max.apply(null, logs.map(function(l) { return l.id; })) : 0;
                localStorage.setItem(STORAGE_KEY, maxId);
            });
        }
        pollLogs();
        setInterval(pollLogs, 20000);

        const enableBtn = document.getElementById('ccai-enable-alerts');
        if (enableBtn) {
            if (window.Notification && Notification.permission === 'granted') {
                enableBtn.textContent = '🔔 Alerts On';
                enableBtn.disabled = true;
            }
            enableBtn.addEventListener('click', function() {
                // Create/resume the AudioContext synchronously, inside the
                // click handler itself, BEFORE requesting notification
                // permission. requestPermission() shows a real OS/browser
                // dialog and its .then() callback fires well after the user
                // gesture has expired, so any audio unlock attempted in
                // there is too late and gets silently suspended forever.
                if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume();
                }
                playBeep(1000, 1);

                if (window.Notification) {
                    Notification.requestPermission().then(function(perm) {
                        if (perm === 'granted') {
                            enableBtn.textContent = '🔔 Alerts On';
                            enableBtn.disabled = true;
                        }
                    });
                }
            });
        }
    });
})();
</script>
<style>
@keyframes ccaiSlideIn {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
}
</style>
"""

def get_shared_layout(page_title: str, main_content: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CareCompanionAI - {page_title}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
            body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        </style>
    </head>
    <body class="bg-gradient-to-tr from-slate-950 via-slate-900 to-indigo-950 min-h-screen text-slate-100 antialiased">
        <div class="flex flex-col md:flex-row min-h-screen">
            <aside class="w-full md:w-64 bg-white/5 border-b md:border-b-0 md:border-r border-white/10 backdrop-blur-xl p-6 flex flex-col justify-between shrink-0 gap-6">
                <div>
                    <div class="mb-8">
                        <h1 class="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">🛡️ CareCompanion</h1>
                        <span class="text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded-full font-bold mt-2 inline-block">PRODUCTION NODE ACTIVE</span>
                    </div>
                    <nav class="space-y-2">
                        <a href="/" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl hover:bg-white/10 text-slate-300 transition font-semibold text-sm block">
                            <span>🏠</span> <span>Entry Dashboard</span>
                        </a>
                        <a href="/medicines" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl hover:bg-white/10 text-slate-300 transition font-semibold text-sm block">
                            <span>💊</span> <span>Add Medicines</span>
                        </a>
                        <a href="/appointments" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl hover:bg-white/10 text-slate-300 transition font-semibold text-sm block">
                            <span>🏥</span> <span>Add Appointments</span>
                        </a>
                        <a href="/caregiver/setup" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl hover:bg-white/10 text-slate-300 transition font-semibold text-sm block">
                            <span>👤</span> <span>Caregiver Details</span>
                        </a>
                        <a href="/caregiver/logs" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl hover:bg-white/10 text-slate-300 transition font-semibold text-sm block">
                            <span>🚨</span> <span>Caregiver Messages</span>
                        </a>
                    </nav>
                </div>
                <div class="border-t border-white/10 pt-4 space-y-2">
                    <button id="ccai-enable-alerts" class="w-full flex items-center justify-center space-x-2 px-4 py-2 rounded-xl bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 text-indigo-300 transition font-semibold text-xs">🔔 Enable Alerts</button>
                    <div class="text-[11px] text-slate-500 px-4">True Multi-Page Routing Stack v3.2</div>
                </div>
            </aside>
            <main class="flex-1 p-6 md:p-10 max-w-5xl mx-auto w-full overflow-hidden">
                {main_content}
            </main>
        </div>
        {ALERTS_SCRIPT}
    </body>
    </html>
    """

# -----------------------------------------------------------------------------
# REAL ROUTED PAGES CHANNELS
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def page_home():
    db = SessionLocal()
    medicines = db.query(Medicine).all()
    appointments = db.query(Appointment).all()
    caregivers = db.query(CaregiverProfile).all()
    caregiver_names = ", ".join(c.name for c in caregivers) if caregivers else "None configured"
    db.close()

    med_cards = ""
    for med in medicines:
        status_badge = (
            '<span class="px-2.5 py-0.5 bg-green-500/20 text-green-300 border border-green-500/30 text-xs rounded-full font-bold">Taken</span>'
            if med.is_taken_today else
            '<span class="px-2.5 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs rounded-full font-bold animate-pulse">Pending</span>'
        )
        action = (
            "" if med.is_taken_today else
            f'<form action="/medicines/take/{med.id}" method="POST" class="mt-4"><button type="submit" class="w-full bg-emerald-500 hover:bg-emerald-600 text-white font-bold py-1.5 px-3 rounded-xl transition text-xs">Mark Taken</button></form>'
        )
        schedule_label = "Daily" if med.frequency_type == "daily" else f"Custom Days ({med.selected_days})"
        med_cards += f"""
        <div class="bg-white/5 border border-white/10 rounded-2xl p-4 shadow-md flex flex-col justify-between hover:border-white/20 transition-all">
            <div>
                <div class="flex justify-between items-start mb-2">
                    <h4 class="font-bold text-white text-md">{med.name}</h4>
                    {status_badge}
                </div>
                <p class="text-xs text-slate-300"><span class="text-slate-500">Volume:</span> {med.dosage}</p>
                <p class="text-xs text-slate-300 mt-0.5"><span class="text-slate-500">Frequency:</span> {schedule_label}</p>
                <p class="text-xs text-indigo-300 font-semibold mt-2">🕒 Time: {med.scheduled_time}</p>
            </div>
            {action}
        </div>
        """

    appt_rows = ""
    for appt in appointments:
        doc = f'<a href="/{appt.prescription_path}" download class="text-cyan-400 text-xs underline">Download Document</a>' if appt.prescription_path else '<span class="text-slate-500 text-xs">None</span>'
        appt_rows += f"""<tr class="border-b border-white/5 text-xs hover:bg-white/5 transition">
            <td class="py-3 font-semibold text-white">{appt.doctor_name} <span class="text-slate-400 font-normal">({appt.specialty})</span></td>
            <td class="py-3 text-slate-300">{appt.date_time}</td>
            <td class="py-3 text-slate-300">{appt.hospital}</td>
            <td class="py-3">{doc}</td>
        </tr>"""

    content = f"""
    <div class="space-y-8">
        <div class="border-b border-white/10 pb-4">
            <h2 class="text-3xl font-extrabold text-white">Central Ecosystem Dashboard</h2>
            <p class="text-slate-400 text-sm">System Welcome Screen. Linked Caregiver(s): <span class="text-indigo-300 font-bold">{caregiver_names}</span></p>
        </div>
        
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="bg-white/5 border border-white/10 rounded-2xl p-6">
                <h3 class="text-lg font-bold mb-4 text-slate-200">Current Medication Intakes</h3>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">{med_cards if med_cards else '<p class="text-slate-500 text-xs col-span-2 italic">No medications scheduled in database storage nodes.</p>'}</div>
            </div>
            <div class="bg-white/5 border border-white/10 rounded-2xl p-6">
                <h3 class="text-lg font-bold mb-4 text-slate-200">Consultation Schedules Overview</h3>
                <div class="overflow-x-auto"><table class="w-full text-left"><thead><tr class="border-b border-white/10 text-slate-400 text-[10px] uppercase font-bold"><th class="pb-2">Doctor</th><th class="pb-2">Time</th><th class="pb-2">Facility</th><th class="pb-2">Records</th></tr></thead><tbody>{appt_rows if appt_rows else '<tr><td colspan="4" class="text-slate-500 text-xs py-4 italic">No clinical schedules recorded.</td></tr>'}</tbody></table></div>
            </div>
        </div>
    </div>
    """
    return HTMLResponse(content=get_shared_layout("Home Entry", content))

# PAGE ROUTE 2: ADD MEDICINES VIEW (URL: /medicines)
@app.get("/medicines", response_class=HTMLResponse)
def page_medicines():
    content = """
    <div class="space-y-6 max-w-xl">
        <div class="border-b border-white/10 pb-4">
            <h2 class="text-2xl font-extrabold text-white">Register Medications</h2>
            <p class="text-slate-400 text-sm">Add clinical tracking routines and customized frequency day indices.</p>
        </div>
        <form action="/medicines/add" method="POST" class="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-4 shadow-xl">
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">MEDICINE FULL NAME</label>
                <input type="text" name="name" required placeholder="e.g., Metformin" class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">DOSAGE FORM/VOLUME</label>
                <input type="text" name="dosage" required placeholder="e.g., 500mg (1 Tablet)" class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">REPETITIVE DAILY ALARM TRIGGER TIME</label>
                <input type="time" name="scheduled_time" required class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">INTAKE FREQUENCY LAYER</label>
                <select name="frequency_type" id="freq-select" onchange="toggleDayMatrix()" class="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
                    <option value="daily">Run Daily Alarms</option>
                    <option value="custom">Run Only on Selected Custom Days</option>
                </select>
            </div>
            <div id="day-matrix-panel" class="hidden bg-black/10 border border-white/5 p-4 rounded-xl space-y-2">
                <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Select Target Weekdays</label>
                <div class="grid grid-cols-2 gap-2 text-xs">
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Monday" class="rounded"> <span>Monday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Tuesday" class="rounded"> <span>Tuesday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Wednesday" class="rounded"> <span>Wednesday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Thursday" class="rounded"> <span>Thursday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Friday" class="rounded"> <span>Friday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Saturday" class="rounded"> <span>Saturday</span></label>
                    <label class="flex items-center space-x-2"><input type="checkbox" name="days" value="Sunday" class="rounded"> <span>Sunday</span></label>
                </div>
            </div>
            <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 px-4 rounded-xl transition text-xs tracking-wider uppercase shadow-lg shadow-indigo-600/20">Commit Schedule</button>
        </form>
    </div>
    <script>
        // Inline layout logic showing checkboxes only when 'custom' is picked
        function toggleDayMatrix() {
            const select = document.getElementById('freq-select');
            const panel = document.getElementById('day-matrix-panel');
            if (select.value === 'custom') {
                panel.classList.remove('hidden');
            } else {
                panel.classList.add('hidden');
            }
        }
    </script>
    """
    return HTMLResponse(content=get_shared_layout("Add Medicines", content))

# PAGE ROUTE 3: ADD APPOINTMENTS VIEW (URL: /appointments)
@app.get("/appointments", response_class=HTMLResponse)
def page_appointments():
    content = """
    <div class="space-y-6 max-w-xl">
        <div class="border-b border-white/10 pb-4">
            <h2 class="text-2xl font-extrabold text-white">Register Clinical Consultations</h2>
            <p class="text-slate-400 text-sm">Schedule upcoming physician consultations and upload clinical reports.</p>
        </div>
        <form action="/appointments/add" method="POST" enctype="multipart/form-data" class="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-4 shadow-xl">
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">PHYSICIAN FULL NAME</label>
                <input type="text" name="doctor_name" required placeholder="Dr. Sarah Jenkins" class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">CLINICAL SPECIALTY FIELD</label>
                <input type="text" name="specialty" required placeholder="Cardiology" class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">DATE & TIME CEILING SLOT</label>
                <input type="datetime-local" name="date_time" required class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">HOSPITAL BASE / CLINIC VENUE</label>
                <input type="text" name="hospital" required placeholder="St. Jude Medical Center" class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">ATTACH PRESCRIPTION SCAN OR DOCUMENT</label>
                <input type="file" name="prescription" class="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-indigo-500/20 file:text-indigo-300 hover:file:bg-indigo-500/30 file:transition">
            </div>
            <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 px-4 rounded-xl transition text-xs tracking-wider uppercase shadow-lg shadow-emerald-600/20">Commit Appointment</button>
        </form>
    </div>
    """
    return HTMLResponse(content=get_shared_layout("Add Appointments", content))

# PAGE ROUTE 4: CAREGIVER CONFIGURATION SETUP VIEW (URL: /caregiver/setup)
@app.get("/caregiver/setup", response_class=HTMLResponse)
def page_caregiver_setup():
    db = SessionLocal()
    caregivers = db.query(CaregiverProfile).all()
    db.close()

    caregiver_cards = ""
    for cg in caregivers:
        caregiver_cards += f"""
        <div class="bg-white/5 border border-white/10 rounded-2xl p-5 shadow-xl flex justify-between items-start">
            <div>
                <p class="text-sm">Name: <span class="text-white font-bold">{cg.name}</span></p>
                <p class="text-sm mt-1">Phone: <span class="text-white font-mono">{cg.phone}</span></p>
                <p class="text-sm mt-1">Email: <span class="text-white font-mono">{cg.email}</span></p>
            </div>
            <form action="/caregiver/delete/{cg.id}" method="POST">
                <button type="submit" class="bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30 text-xs font-bold px-3 py-1.5 rounded-xl transition">Remove</button>
            </form>
        </div>
        """
    if not caregiver_cards:
        caregiver_cards = '<p class="text-slate-500 text-xs italic">No caregivers added yet.</p>'

    content = f"""
    <div class="space-y-6 max-w-xl">
        <div class="border-b border-white/10 pb-4">
            <h2 class="text-2xl font-extrabold text-white">Caregiver Node Configuration</h2>
            <p class="text-slate-400 text-sm">Add one or more caregivers to receive alert and compliance messages.</p>
        </div>
        <div class="space-y-4">
            <h3 class="text-xs font-bold text-slate-400 uppercase tracking-widest">Registered Caregivers ({len(caregivers)})</h3>
            {caregiver_cards}
        </div>
        <form action="/caregiver/add" method="POST" class="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-4 shadow-xl">
            <h3 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Add New Caregiver</h3>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">CAREGIVER NAME</label>
                <input type="text" name="name" required class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">MOBILE CONTACT LINK</label>
                <input type="text" name="phone" required class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">EMAIL DOMAIN PATH</label>
                <input type="email" name="email" required class="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 transition">
            </div>
            <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 px-4 rounded-xl transition text-xs tracking-wider uppercase">Add Caregiver</button>
        </form>
    </div>
    """
    return HTMLResponse(content=get_shared_layout("Caregiver Setup", content))

# PAGE ROUTE 5: CAREGIVER DUAL TELEMETRY LOGGER (URL: /caregiver/logs)
@app.get("/caregiver/logs", response_class=HTMLResponse)
def page_caregiver_logs():
    content = """
    <div class="space-y-6">
        <div class="border-b border-white/10 pb-4 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-extrabold text-white">Caregiver Telemetry Messages Audit</h2>
                <p class="text-slate-400 text-sm">Verification space printing dual states (Intake Confirmed vs 10-Min Escalation alerts).</p>
            </div>
            <button onclick="fetchLogs()" class="bg-white/10 hover:bg-white/20 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white transition font-medium">🔄 Flush View</button>
        </div>
        <div class="bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl">
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-white">
                    <thead>
                        <tr class="border-b border-white/20 text-slate-400 text-xs uppercase tracking-wider">
                            <th class="pb-3 font-semibold">System Timestamp</th>
                            <th class="pb-3 font-semibold">Medicine Item</th>
                            <th class="pb-3 font-semibold">Target Receiver</th>
                            <th class="pb-3 font-semibold">Dispatched Metric Message</th>
                        </tr>
                    </thead>
                    <tbody id="real-log-rows">
                        <tr><td colspan="4" class="py-4 text-center text-slate-500 text-xs italic">Syncing messaging registers...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        async function fetchLogs() {
            try {
                const res = await fetch('/api/raw/logs');
                const logs = await res.json();
                const tbody = document.getElementById('real-log-rows');
                tbody.innerHTML = '';
                
                if(logs.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-500 text-xs italic">No entries generated for current tracking timeline loop.</td></tr>`;
                    return;
                }
                
                logs.forEach(log => {
                    const badgeColor = log.event_type === 'SUCCESS' ? 'bg-green-500/20 text-green-300 border-green-500/30' : 'bg-red-500/20 text-red-300 border-red-500/30';
                    tbody.innerHTML += `
                        <tr class="border-b border-white/5 hover:bg-white/5 transition text-xs">
                            <td class="py-3 font-mono text-yellow-400">${log.timestamp}</td>
                            <td class="py-3 font-bold text-slate-200">${log.medicine_name}</td>
                            <td class="py-3 text-slate-300">${log.recipient}</td>
                            <td class="py-3">
                                <span class="px-2 py-0.5 border rounded-full text-[10px] font-bold ${badgeColor}">
                                    ${log.status}
                                </span>
                            </td>
                        </tr>
                    `;
                });
            } catch(e) { console.error(e); }
        }
        document.addEventListener("DOMContentLoaded", () => {
            fetchLogs();
            setInterval(fetchLogs, 5000);
        });
    </script>
    """
    return HTMLResponse(content=get_shared_layout("Caregiver Messages", content))

# -----------------------------------------------------------------------------
# ACTION PROCESSING BACKEND LOGIC PIPELINES
# -----------------------------------------------------------------------------
@app.get("/api/raw/logs")
def api_raw_logs():
    db = SessionLocal()
    try:
        return db.query(NotificationLog).order_by(NotificationLog.id.desc()).all()
    finally:
        db.close()

@app.post("/medicines/add")
def action_add_med(
    request: Request,
    name: str = Form(...), 
    dosage: str = Form(...), 
    scheduled_time: str = Form(...),
    frequency_type: str = Form(...),
):
    # Synchronously parse custom list elements from multi-select options if custom frequency is flagged
    db = SessionLocal()
    try:
        days_string = "All"
        if frequency_type == "custom":
            async def parse_form_body():
                form_data = await request.form()
                return form_data.getlist("days")
            selected_days_list = asyncio.run(parse_form_body())
            days_string = ",".join(selected_days_list) if selected_days_list else "Monday"

        db.add(Medicine(
            name=name, dosage=dosage, scheduled_time=scheduled_time,
            frequency_type=frequency_type, selected_days=days_string
        ))
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/medicines/take/{med_id}")
def action_take_med(med_id: int):
    db = SessionLocal()
    med = db.query(Medicine).filter(Medicine.id == med_id).first()
    caregivers = db.query(CaregiverProfile).all()
    recipient_label = ", ".join(f"{c.name} ({c.phone})" for c in caregivers) if caregivers else "No caregivers configured"

    if med:
        med.is_taken_today = True
        
        # LOG SUCCESS INTENT PIECE DIRECTLY INTO AUDIT MATRIX ROOM
        db.add(NotificationLog(
            medicine_name=med.name,
            recipient=recipient_label,
            status="SUCCESS: Medicine verified taken on time!",
            event_type="SUCCESS"
        ))
        db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/appointments/add")
async def action_add_appt(
    doctor_name: str = Form(...), specialty: str = Form(...),
    date_time: str = Form(...), hospital: str = Form(...),
    prescription: UploadFile = File(None)
):
    db = SessionLocal()
    formatted_dt = date_time.replace("T", " ")
    file_path = None
    if prescription and prescription.filename:
        file_path = os.path.join(UPLOAD_DIR, f"{int(datetime.now().timestamp())}_{prescription.filename}")
        with open(file_path, "wb") as buffer:
            buffer.write(await prescription.read())
            
    db.add(Appointment(doctor_name=doctor_name, specialty=specialty, date_time=formatted_dt, hospital=hospital, prescription_path=file_path))
    db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/caregiver/add")
def action_add_cg(name: str = Form(...), phone: str = Form(...), email: str = Form(...)):
    db = SessionLocal()
    db.add(CaregiverProfile(name=name, phone=phone, email=email))
    db.commit()
    db.close()
    return RedirectResponse(url="/caregiver/setup", status_code=303)

@app.post("/caregiver/delete/{cg_id}")
def action_delete_cg(cg_id: int):
    db = SessionLocal()
    cg = db.query(CaregiverProfile).filter(CaregiverProfile.id == cg_id).first()
    if cg:
        db.delete(cg)
        db.commit()
    db.close()
    return RedirectResponse(url="/caregiver/setup", status_code=303)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main.py:app" if "__file__" not in globals() else f"{os.path.basename(__file__)[:-3]}:app", host="0.0.0.0", port=port, reload=False)