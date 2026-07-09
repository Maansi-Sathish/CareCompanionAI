from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

DATABASE_URL = "sqlite:///./carecompanion.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Caregiver(Base):
    __tablename__ = "caregivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)  # E.164 format: +1234567890

class Medication(Base):
    __tablename__ = "medications"
    id = Column(Integer, primary_key=True, index=True)
    tablet_name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)          # e.g., "1 tablet"
    timings = Column(String, nullable=False)         # Comma-separated, e.g., "09:00, 21:00"
    days = Column(String, nullable=False)            # e.g., "Daily", "Mon,Wed,Fri"
    is_taken_today = Column(Boolean, default=False)

class DoctorVisit(Base):
    __tablename__ = "doctor_visits"
    id = Column(Integer, primary_key=True, index=True)
    doctor_name = Column(String, nullable=False)
    visit_date = Column(DateTime, nullable=False)
    specialty = Column(String, nullable=True)
    status = Column(String, default="Scheduled")     # Scheduled, Completed
    prescription_path = Column(String, nullable=True) # File storage locator

def init_db():
    Base.metadata.create_all(bind=engine)