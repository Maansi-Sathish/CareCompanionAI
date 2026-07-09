# 🛡️ CareCompanionAI

CareCompanionAI is an intelligent, multi-page healthcare management system designed to help elderly individuals manage their medications and doctor appointments while keeping caregivers informed. The application runs native background monitoring agents to provide real-time hardware medication reminders, schedule upcoming doctor visits, preserve prescription records, and execute safety escalation alerts to caregivers if a dose is skipped.

## 🌟 Core Features

- **Clinical Planner Dashboard:** Seamlessly add and track medications with precise dosage, 24-hour schedules, and custom day intervals.
- **Hardware Audio Reminders:** Active background agent scripts trigger physical motherboard buzzer tones (`winsound`) exactly when a medication is due.
- **Smart Safety Escalation:** Automatically monitors compliance and alerts registered emergency caregivers if a medication status is left pending 10 minutes past its scheduled window.
- **Consultation Scheduler:** Track upcoming doctor visits with date, time, and medical specialties, with an integrated pre-departure alarm buzzer 30 minutes before the appointment.
- **Prescription Preservation:** Securely upload and store medical prescriptions and documents linked directly to their specific clinical visit.
- **Asynchronous Auto-Reset:** Intelligent background synchronization worker resets the global daily compliance registry back to pending status at midnight sharp for the new calendar day.

## 🛠️ Tech Stack

**Frontend Interface**
- Asynchronous Vanilla JavaScript (ES6+ State Routing Engine)
- Tailwind CSS (Fluid Glassmorphic UI Dashboard Architecture)

**Backend Core**
- FastAPI (High-performance ASGI Framework)
- Python Asynchronous Event Loops (`asyncio` Worker Threads)

**Database & Storage**
- SQLite (Embedded Lightweight Relational Database File)
- SQLAlchemy (Object-Relational Mapping Engine)

**System Hardware Integration**
- Native OS Execution Drivers (Win32 `winsound` / Terminal Bell fallback)

## 📁 Project Structure

```text
CareCompanionAI/
├── main.py              # Unified Asynchronous Application Core
├── carecompanion.db     # Local SQLite Relational Database Engine (Auto-generated)
├── requirements.txt     # Cloud Deployment Package Manifest
├── .gitignore           # Version Control Exclusion Matrix
└── 📁 uploads/          # Local & Permanent Storage for Prescription Documents