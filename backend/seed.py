"""Creates tables, the first admin, and optional demo data.
   python seed.py          -> tables + admin only
   python seed.py --demo   -> also sample positions, candidates and 5 voters with demo email/phone
Voters sign in with their matric number and a one-time code sent to the email/phone stored below."""
import os
import sys

from core.db import SessionLocal, init_db
from core.models import Admin, Candidate, Position
from core.security import hash_pw
from core import services

init_db()
db = SessionLocal()

username = os.getenv("ADMIN_USERNAME", "admin")
if not db.query(Admin).filter_by(username=username).first():
    db.add(Admin(username=username, full_name="System Administrator",
                 password_hash=hash_pw(os.getenv("ADMIN_PASSWORD", "ChangeMe123!"))))
    db.commit()
    print(f"Admin created: {username}")

if "--demo" in sys.argv and not db.query(Position).count():
    for order, (title, names) in enumerate([
        ("President", ["Amina Yusuf", "Chidi Okafor"]),
        ("Vice President", ["Tunde Bello", "Grace Eze"]),
        ("General Secretary", ["Ibrahim Musa", "Ngozi Obi"]),
    ], start=1):
        p = Position(title=title, display_order=order)
        p.candidates = [Candidate(full_name=n, department="Computer Science", level="ND2") for n in names]
        db.add(p)
    db.commit()
    rows = [{"matric_no": f"DEMO/00{i}", "full_name": f"Demo Voter {i}", "email": f"demo{i}@example.com",
             "phone": f"0801000000{i}", "department": d, "level": l}
            for i, (d, l) in enumerate([("Computer Science", "ND1"), ("Computer Science", "ND2"),
                                        ("Electrical Eng.", "HND1"), ("Accountancy", "ND2"),
                                        ("Accountancy", "HND2")], start=1)]
    res = services.import_voters(db, rows)
    print(f"  {len(res['created'])} demo voters: DEMO/001 .. DEMO/005 (email demoN@example.com, phone 0801000000N)")
    print("  Set OTP_DEV_MODE=true in .env to see their one-time codes in the API console.")
