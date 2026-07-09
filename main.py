import os
import sys
import asyncio
import shutil
from datetime import datetime, timedelta
from typing import Optional

# Core Framework Dependencies
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel

# =====================================================================
# 1. DATABASE MODELS & CONFIGURATION
# =====================================================================
DATABASE_URL = "sqlite:///./carecompanion.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Caregiver(Base):
    __tablename__ = "caregivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)

class Medication(Base):
    __tablename__ = "medications"
    id = Column(Integer, primary_key=True, index=True)
    tablet_name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)          
    timings = Column(String, nullable=False)         
    days = Column(String, nullable=False)            
    is_taken_today = Column(Boolean, default=False)

class DoctorVisit(Base):
    __tablename__ = "doctor_visits"
    id = Column(Integer, primary_key=True, index=True)
    doctor_name = Column(String, nullable=False)
    visit_date = Column(DateTime, nullable=False)
    specialty = Column(String, nullable=True)
    status = Column(String, default="Scheduled")     
    prescription_path = Column(String, nullable=True) 

# =====================================================================
# 2. APP SETUP & REGULATED BACKGROUND TASK AGENTS
# =====================================================================
app = FastAPI(title="CareCompanionAI", version="2.0.0")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/prescriptions", StaticFiles(directory=UPLOAD_DIR), name="prescriptions")

Base.metadata.create_all(bind=engine)

def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()

def trigger_system_beep(frequency=1000, duration_ms=800, repetitions=3):
    print(f"🔊 [AUDIO AGENT] Launching hardware alarm beep sequence ({frequency}Hz)...")
    for _ in range(repetitions):
        if sys.platform == "win32":
            import winsound
            winsound.Beep(frequency, duration_ms)
        else:
            sys.stdout.write('\a')
            sys.stdout.flush()
        import time
        time.sleep(0.1)

async def medication_alarm_monitor():
    while True:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        database = SessionLocal()
        try:
            medications = database.query(Medication).all()
            for med in medications:
                scheduled_times = [t.strip() for t in med.timings.split(",")]
                for t_str in scheduled_times:
                    try:
                        if t_str == current_time_str:
                            trigger_system_beep(frequency=1100, duration_ms=600, repetitions=3)
                        
                        sched_time = datetime.strptime(t_str, "%H:%M").time()
                        sched_datetime = datetime.combine(now.date(), sched_time)
                        ten_mins_after = sched_datetime + timedelta(minutes=10)
                        
                        if now.hour == ten_mins_after.hour and now.minute == ten_mins_after.minute:
                            if not med.is_taken_today:
                                trigger_system_beep(frequency=2100, duration_ms=400, repetitions=5)
                                caregivers = database.query(Caregiver).all()
                                for cg in caregivers:
                                    print(f"📱 [ALERT] Escalated to {cg.name} ({cg.phone_number}): Missed {med.tablet_name}")
                    except Exception:
                        pass
        finally:
            database.close()
        await asyncio.sleep(60)

async def doctor_visit_monitor():
    while True:
        now = datetime.now()
        database = SessionLocal()
        try:
            visits = database.query(DoctorVisit).filter(DoctorVisit.status == "Scheduled").all()
            for visit in visits:
                thirty_mins_before = visit.visit_date - timedelta(minutes=30)
                if now.date() == thirty_mins_before.date() and now.hour == thirty_mins_before.hour and now.minute == thirty_mins_before.minute:
                    trigger_system_beep(frequency=750, duration_ms=1000, repetitions=2)
        finally:
            database.close()
        await asyncio.sleep(60)

async def daily_midnight_reset_worker():
    while True:
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        next_midnight = datetime.combine(tomorrow, datetime.min.time())
        await asyncio.sleep((next_midnight - now).total_seconds() + 1)
        database = SessionLocal()
        try:
            database.query(Medication).update({Medication.is_taken_today: False})
            database.commit()
        finally:
            database.close()

@app.on_event("startup")
async def start_monitors():
    asyncio.create_task(medication_alarm_monitor())
    asyncio.create_task(doctor_visit_monitor())
    asyncio.create_task(daily_midnight_reset_worker())

# =====================================================================
# 3. ADVANCED ARCHITECTURAL FRONTEND EMBEDDING
# =====================================================================
@app.get("/", response_class=HTMLResponse)
def render_dashboard(database: Session = Depends(get_db)):
    meds = database.query(Medication).all()
    visits = database.query(DoctorVisit).all()
    caregivers = database.query(Caregiver).all()
    
    # Pre-calculate counts for Welcome view analytics
    taken_count = sum(1 for m in meds if m.is_taken_today)
    total_meds = len(meds)
    scheduled_visits = sum(1 for v in visits if v.status == "Scheduled")

    # Generate dynamic tables and rows
    med_rows = ""
    for m in meds:
        status = '<span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs px-3 py-1 rounded-full font-medium">Completed</span>' if m.is_taken_today else '<span class="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs px-3 py-1 rounded-full font-medium">Awaiting Ingestion</span>'
        btn = "" if m.is_taken_today else f'<button onclick="takeMed({m.id})" class="bg-gradient-to-r from-teal-500 to-emerald-500 hover:scale-105 transition active:scale-95 text-white text-xs font-semibold px-4 py-1.5 rounded-xl shadow-lg shadow-emerald-500/10">Mark Taken</button>'
        med_rows += f"""
        <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition duration-150">
            <td class="px-6 py-4 font-semibold text-slate-200">{m.tablet_name}</td>
            <td class="px-6 py-4 text-slate-400">{m.dosage}</td>
            <td class="px-6 py-4 font-mono text-teal-400">{m.timings}</td>
            <td class="px-6 py-4">{status}</td>
            <td class="px-6 py-4 text-right">{btn}</td>
        </tr>
        """

    visit_cards = ""
    for v in visits:
        action = f'<a href="{v.prescription_path}" target="_blank" class="text-teal-400 hover:text-teal-300 font-semibold mt-3 inline-block text-sm flex items-center gap-1">📄 View Prescription Document →</a>' if v.prescription_path else f"""
        <form onsubmit="uploadPrescription(event, {v.id})" class="mt-4 flex items-center gap-2">
            <input type="file" required class="block w-full text-xs text-slate-400 bg-slate-900 border border-slate-700 rounded-lg cursor-pointer file:bg-slate-800 file:border-none file:text-white file:px-3 file:py-1 file:mr-2">
            <button type="submit" class="bg-slate-700 text-white text-xs px-3 py-1 rounded-lg hover:bg-slate-600 font-medium">Attach</button>
        </form>
        """
        visit_cards += f"""
        <div class="p-5 bg-slate-800/30 border border-slate-700/40 rounded-2xl backdrop-blur-md">
            <div class="flex justify-between items-start">
                <div>
                    <h5 class="text-lg font-bold text-slate-100">Dr. {v.doctor_name}</h5>
                    <p class="text-xs text-teal-400 font-semibold tracking-wider uppercase">{v.specialty or "General Health"}</p>
                </div>
                <span class="text-xs font-mono font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full { 'bg-amber-500/10 text-amber-400 border border-amber-500/20' if v.status == 'Scheduled' else 'bg-slate-500/10 text-slate-400 border border-slate-700/50' }">{v.status}</span>
            </div>
            <p class="text-sm text-slate-400 mt-3 flex items-center gap-2">⏰ {v.visit_date.strftime('%B %d, %Y at %I:%M %p')}</p>
            {action}
        </div>
        """

    cg_cards = ""
    for c in caregivers:
        cg_cards += f"""
        <div class="p-4 bg-slate-800/40 border border-slate-700/50 rounded-xl flex justify-between items-center">
            <div>
                <p class="font-bold text-slate-200">{c.name}</p>
                <p class="text-xs text-slate-400 font-mono">{c.phone_number}</p>
            </div>
            <div class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>CareCompanionAI | Intelligent Portal</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
            body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
            .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
            .glass {{ background: rgba(30, 41, 59, 0.45); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.05); }}
            .nav-active {{ background: rgba(20, 184, 166, 0.15); color: #2dd4bf; border-left: 4px solid #2dd4bf; }}
        </style>
    </head>
    <body class="bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100 min-h-screen flex">

        <aside class="w-72 bg-slate-900/90 border-r border-slate-800/80 flex flex-col justify-between p-6">
            <div class="space-y-8">
                <div class="flex items-center gap-3">
                    <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg shadow-teal-500/20">🛡️</div>
                    <div>
                        <h1 class="text-lg font-extrabold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">CareCompanion</h1>
                        <p class="text-[10px] font-mono tracking-widest text-teal-400 uppercase">Agent Ecosystem</p>
                    </div>
                </div>

                <nav class="space-y-1.5">
                    <button id="btn-welcome" onclick="showPage('page-welcome')" class="w-full flex items-center gap-3.5 px-4 py-3 text-sm font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 rounded-xl transition duration-150 text-left">🏠 Home Welcome Hub</button>
                    <button id="btn-caregiver" onclick="showPage('page-caregiver')" class="w-full flex items-center gap-3.5 px-4 py-3 text-sm font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 rounded-xl transition duration-150 text-left">👥 Caregiver Management</button>
                    <button id="btn-medical" onclick="showPage('page-medical')" class="w-full flex items-center gap-3.5 px-4 py-3 text-sm font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 rounded-xl transition duration-150 text-left">💊 Clinical Planner</button>
                </nav>
            </div>

            <div class="p-4 rounded-2xl glass flex items-center gap-3 border border-teal-500/10">
                <div class="relative h-3 w-3 flex justify-center items-center">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                </div>
                <div class="text-xs font-mono text-slate-400">Core Agent: <span class="text-teal-400 font-bold">Online</span></div>
            </div>
        </aside>

        <main class="flex-1 p-10 max-h-screen overflow-y-auto">

            <section id="page-welcome" class="space-y-8 hidden">
                <div class="max-w-4xl space-y-2">
                    <h2 class="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-500 bg-clip-text text-transparent">Welcome to CareCompanionAI</h2>
                    <p class="text-slate-400 text-base max-w-2xl">An active background system monitoring real-time medication timing registers, executing physical auditory alarms, and processing emergency automated caregiver communication pipelines.</p>
                </div>

                <div class="grid grid-cols-3 gap-6 max-w-4xl">
                    <div class="p-6 rounded-3xl glass space-y-2">
                        <p class="text-xs font-mono uppercase text-teal-400 tracking-wider">Ingestion Rate</p>
                        <p class="text-3xl font-black text-white font-mono">{taken_count} / {total_meds}</p>
                        <p class="text-xs text-slate-400">Medications processed today</p>
                    </div>
                    <div class="p-6 rounded-3xl glass space-y-2">
                        <p class="text-xs font-mono uppercase text-purple-400 tracking-wider">Consultations Scheduled</p>
                        <p class="text-3xl font-black text-white font-mono">{scheduled_visits}</p>
                        <p class="text-xs text-slate-400">Upcoming clinical checkups</p>
                    </div>
                    <div class="p-6 rounded-3xl glass space-y-2">
                        <p class="text-xs font-mono uppercase text-emerald-400 tracking-wider">Active Controllers</p>
                        <p class="text-3xl font-black text-white font-mono">{len(caregivers)}</p>
                        <p class="text-xs text-slate-400">Registered emergency contacts</p>
                    </div>
                </div>

                <div class="max-w-4xl p-6 rounded-3xl bg-gradient-to-r from-slate-900 to-slate-800/40 border border-slate-800/80 space-y-4">
                    <h3 class="text-lg font-bold text-slate-200">System Checklist Instructions</h3>
                    <div class="grid grid-cols-2 gap-4 text-sm text-slate-400">
                        <div class="flex gap-3"><span class="text-teal-400 font-bold">1.</span> Configure emergency caregiver parameters under the management tab.</div>
                        <div class="flex gap-3"><span class="text-purple-400 font-bold">2.</span> Schedule medication indices with precise 24-hour timestamp patterns.</div>
                    </div>
                </div>
            </section>


            <section id="page-caregiver" class="space-y-6 max-w-2xl hidden">
                <div>
                    <h2 class="text-3xl font-extrabold text-white tracking-tight">Caregiver Management</h2>
                    <p class="text-sm text-slate-400 mt-1">Register system controllers responsible for handling algorithmic medication omissions.</p>
                </div>

                <div class="p-6 rounded-3xl glass space-y-4">
                    <h3 class="text-lg font-bold text-slate-200">Register New Controller Contact</h3>
                    <form onsubmit="addCaregiver(event)" class="space-y-4">
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-[11px] font-mono tracking-wider uppercase text-slate-400 mb-1">Full Name</label>
                                <input id="cg_name" type="text" required class="w-full bg-slate-900/60 border border-slate-700/60 rounded-xl p-2.5 text-sm text-white focus:outline-none focus:border-teal-500">
                            </div>
                            <div>
                                <label class="block text-[11px] font-mono tracking-wider uppercase text-slate-400 mb-1">Phone Number (+1...)</label>
                                <input id="cg_phone" type="text" required class="w-full bg-slate-900/60 border border-slate-700/60 rounded-xl p-2.5 text-sm text-white focus:outline-none focus:border-teal-500">
                            </div>
                        </div>
                        <button type="submit" class="w-full bg-gradient-to-r from-teal-500 to-emerald-500 text-slate-950 font-bold text-xs py-3 rounded-xl transition hover:opacity-90 uppercase tracking-wider">Save Identity Profile</button>
                    </form>
                </div>

                <div class="space-y-3">
                    <h3 class="text-sm font-mono uppercase tracking-wider text-slate-400">Active Controllers</h3>
                    <div class="space-y-2">{cg_cards or '<p class="text-slate-500 text-sm italic">No emergency profiles logged.</p>'}</div>
                </div>
            </section>


            <section id="page-medical" class="space-y-8 hidden">
                <div class="flex justify-between items-center">
                    <div>
                        <h2 class="text-3xl font-extrabold text-white tracking-tight">Clinical Planner</h2>
                        <p class="text-sm text-slate-400 mt-1">Track schedules, confirm medicine intake, and manage doctor checkups.</p>
                    </div>
                    <div class="flex gap-3">
                        <button onclick="toggleModal('med-modal')" class="bg-teal-500/10 border border-teal-500/20 hover:bg-teal-500/20 text-teal-400 text-xs font-bold px-4 py-2.5 rounded-xl transition">Add Medication</button>
                        <button onclick="toggleModal('visit-modal')" class="bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/20 text-purple-400 text-xs font-bold px-4 py-2.5 rounded-xl transition">Schedule Visit</button>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-8">
                    <div class="xl:col-span-2 space-y-4">
                        <h3 class="text-lg font-bold text-slate-200">Daily Medication Checklist</h3>
                        <div class="rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden shadow-xl">
                            <table class="w-full text-sm text-left text-slate-400">
                                <thead class="text-xs text-slate-400 uppercase bg-slate-900/80 font-mono tracking-wider border-b border-slate-800">
                                    <tr>
                                        <th scope="col" class="px-6 py-4">Tablet Name</th>
                                        <th scope="col" class="px-6 py-4">Dosage</th>
                                        <th scope="col" class="px-6 py-4">Schedule (24hr)</th>
                                        <th scope="col" class="px-6 py-4">Status</th>
                                        <th scope="col" class="px-6 py-4 text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody>{med_rows or '<tr><td colspan="5" class="text-center py-12 text-slate-600 italic">No prescription variables logged in database.</td></tr>'}</tbody>
                            </table>
                        </div>
                    </div>

                    <div class="space-y-4">
                        <h3 class="text-lg font-bold text-slate-200">Doctor Consultations</h3>
                        <div class="space-y-4">{visit_cards or '<div class="p-6 rounded-2xl border border-slate-800/60 text-center text-slate-600 text-sm italic">No scheduled clinic consultations.</div>'}</div>
                    </div>
                </div>
            </section>

        </main>

        <div id="med-modal" class="hidden fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-3xl max-w-md w-full shadow-2xl space-y-4">
                <h3 class="text-xl font-bold text-white">Log Prescription Index</h3>
                <form onsubmit="submitMed(event)" class="space-y-4 text-sm">
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Tablet Name</label><input id="m_name" type="text" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Dosage Details</label><input id="m_dosage" type="text" placeholder="e.g. 1 Caplet" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Timings (24hr CSV pattern)</label><input id="m_timings" type="text" placeholder="e.g. 08:30, 20:00" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Days Interval</label><input id="m_days" type="text" value="Daily" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div class="flex justify-end gap-2 pt-2"><button type="button" onclick="toggleModal('med-modal')" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition">Close</button><button type="submit" class="px-4 py-2 bg-gradient-to-r from-teal-500 to-emerald-500 text-slate-950 font-bold rounded-xl transition opacity-90 hover:opacity-100">Save</button></div>
                </form>
            </div>
        </div>

        <div id="visit-modal" class="hidden fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-3xl max-w-md w-full shadow-2xl space-y-4">
                <h3 class="text-xl font-bold text-white">Schedule Clinical Visit</h3>
                <form onsubmit="submitVisit(event)" class="space-y-4 text-sm">
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Doctor Name</label><input id="v_name" type="text" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Date & Time Target</label><input id="v_date" type="datetime-local" required class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-slate-400 focus:outline-none focus:border-teal-500"></div>
                    <div><label class="block text-xs font-mono uppercase text-slate-400 mb-1">Medical Specialty Field</label><input id="v_spec" type="text" placeholder="e.g. Neurologist" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-white focus:outline-none focus:border-teal-500"></div>
                    <div class="flex justify-end gap-2 pt-2"><button type="button" onclick="toggleModal('visit-modal')" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition">Close</button><button type="submit" class="px-4 py-2 bg-gradient-to-r from-purple-500 to-indigo-500 text-white font-bold rounded-xl transition opacity-90 hover:opacity-100">Confirm</button></div>
                </form>
            </div>
        </div>

        <script>
            // State Preservation Routing Engine
            function showPage(pageId) {{
                ['page-welcome', 'page-caregiver', 'page-medical'].forEach(p => {{
                    document.getElementById(p).classList.add('hidden');
                }});
                ['btn-welcome', 'btn-caregiver', 'btn-medical'].forEach(b => {{
                    document.getElementById(b).classList.remove('nav-active');
                }});
                
                document.getElementById(pageId).classList.remove('hidden');
                const coreBtnId = pageId.replace('page-', 'btn-');
                document.getElementById(coreBtnId).classList.add('nav-active');
                localStorage.setItem('active_view_port', pageId);
            }}

            function toggleModal(id) {{ document.getElementById(id).classList.toggle('hidden'); }}
            
            async function takeMed(id) {{
                const res = await fetch(`/medications/${{id}}/take`, {{ method: 'POST' }});
                if (res.ok) window.location.reload();
            }}

            async function submitMed(e) {{
                e.preventDefault();
                const payload = {{
                    tablet_name: document.getElementById('m_name').value,
                    dosage: document.getElementById('m_dosage').value,
                    timings: document.getElementById('m_timings').value,
                    days: document.getElementById('m_days').value
                }};
                const res = await fetch('/medications/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                if (res.ok) window.location.reload();
            }}

            async function submitVisit(e) {{
                e.preventDefault();
                const payload = {{
                    doctor_name: document.getElementById('v_name').value,
                    visit_date: new Date(document.getElementById('v_date').value).toISOString(),
                    specialty: document.getElementById('v_spec').value
                }};
                const res = await fetch('/visits/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                if (res.ok) window.location.reload();
            }}

            async function addCaregiver(e) {{
                e.preventDefault();
                const payload = {{
                    name: document.getElementById('cg_name').value,
                    phone_number: document.getElementById('cg_phone').value
                }};
                const res = await fetch('/caregivers/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                if (res.ok) window.location.reload();
            }}

            async function uploadPrescription(e, id) {{
                e.preventDefault();
                const fileInput = e.target.querySelector('input[type="file"]');
                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                const res = await fetch(`/visits/${{id}}/upload-prescription`, {{ method: 'POST', body: formData }});
                if (res.ok) window.location.reload();
            }}

            // Restore the last view state on initial page load
            const activeView = localStorage.getItem('active_view_port') || 'page-welcome';
            showPage(activeView);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# =====================================================================
# 4. REST API SPECIFICATIONS
# =====================================================================
class CaregiverCreate(BaseModel):
    name: str
    phone_number: str

class MedicationCreate(BaseModel):
    tablet_name: str
    dosage: str
    timings: str
    days: str

class DoctorVisitCreate(BaseModel):
    doctor_name: str
    visit_date: datetime
    specialty: Optional[str] = None

@app.post("/caregivers/")
def add_caregiver(cg: CaregiverCreate, database: Session = Depends(get_db)):
    new_cg = Caregiver(name=cg.name, phone_number=cg.phone_number)
    database.add(new_cg)
    database.commit()
    return {"status": "success"}

@app.post("/medications/")
def schedule_medication(med: MedicationCreate, database: Session = Depends(get_db)):
    new_med = Medication(**med.model_dump())
    database.add(new_med)
    database.commit()
    return {"status": "success"}

@app.post("/medications/{med_id}/take")
def take_medication(med_id: int, database: Session = Depends(get_db)):
    med = database.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication record absent")
    med.is_taken_today = True
    database.commit()
    return {"status": "success"}

@app.post("/visits/")
def schedule_visit(visit: DoctorVisitCreate, database: Session = Depends(get_db)):
    new_visit = DoctorVisit(**visit.model_dump())
    database.add(new_visit)
    database.commit()
    return {"status": "success"}

@app.post("/visits/{visit_id}/upload-prescription")
async def upload_prescription(visit_id: int, file: UploadFile = File(...), database: Session = Depends(get_db)):
    visit = database.query(DoctorVisit).filter(DoctorVisit.id == visit_id).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit record absent")
    ext = os.path.splitext(file.filename)[1]
    safe_filename = f"visit_{visit_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    visit.prescription_path = f"/prescriptions/{safe_filename}"
    visit.status = "Completed"
    database.commit()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)