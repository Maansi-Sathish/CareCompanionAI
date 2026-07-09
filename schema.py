from pydantic import BaseModel
from datetime import datetime
from typing import Optional

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