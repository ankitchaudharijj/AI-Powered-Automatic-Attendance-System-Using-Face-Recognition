"""
services/attendance_service.py
===============================
Business logic for marking attendance (from face recognition or
manually) and for querying attendance history / search / analytics.

Duplicate prevention strategy (defense in depth):
    1. FaceService cooldown — skip re-processing a face seen < 8s ago.
    2. Explicit pre-check here — skip if today's row already exists.
    3. Database UNIQUE constraint (student_id, subject_id, attendance_date)
       — the authoritative guard even under concurrent requests.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from models import Attendance, AttendanceStatus, MarkedBy, Student, SystemLog, LogLevel
from utils.extensions import db
from utils.logger import get_logger

logger = get_logger(__name__)

# An attendance mark after this hour is flagged as "late" rather than "present".
LATE_CUTOFF_HOUR = 9


class AttendanceService:
    """Encapsulates attendance marking and reporting logic."""

    def mark_attendance(
        self,
        student_id: int,
        subject_id: Optional[int] = None,
        confidence: Optional[float] = None,
        marked_by: str = MarkedBy.FACE_RECOGNITION,
    ) -> Tuple[Optional[Attendance], bool, Optional[str]]:
        """
        Mark a student present for today (optionally for a specific
        subject session).

        Returns:
            (Attendance | None, was_newly_created: bool, error_message | None)
        """
        student = Student.query.get(student_id)
        if student is None:
            return None, False, "Student not found."

        today = date.today()
        now = datetime.now().time()

        existing = Attendance.query.filter_by(
            student_id=student_id, subject_id=subject_id, attendance_date=today
        ).first()
        if existing is not None:
            return existing, False, None  # Already marked — not an error, just a no-op.

        status = AttendanceStatus.LATE if now.hour >= LATE_CUTOFF_HOUR else AttendanceStatus.PRESENT

        record = Attendance(
            student_id=student_id,
            subject_id=subject_id,
            class_id=student.class_id,
            attendance_date=today,
            time_in=now.replace(microsecond=0),
            status=status,
            marked_by=marked_by,
            confidence_score=confidence,
        )

        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            # Race condition: another request marked it in the split second
            # between our SELECT and INSERT. The UNIQUE constraint saved us.
            db.session.rollback()
            existing = Attendance.query.filter_by(
                student_id=student_id, subject_id=subject_id, attendance_date=today
            ).first()
            return existing, False, None

        self._log(
            "ATTENDANCE_MARKED",
            f"Attendance marked for '{student.name}' ({student.roll_number}) via {marked_by}.",
        )
        logger.info("Attendance marked: student_id=%s subject_id=%s status=%s", student_id, subject_id, status)
        return record, True, None

    def mark_manual(
        self, student_id: int, subject_id: Optional[int], admin_username: str
    ) -> Tuple[Optional[Attendance], bool, Optional[str]]:
        """Manually mark a student present (used from the admin UI as a fallback)."""
        record, created, error = self.mark_attendance(student_id, subject_id, marked_by=MarkedBy.MANUAL)
        if created:
            self._log("ATTENDANCE_MANUAL", f"'{admin_username}' manually marked attendance for student_id={student_id}.")
        return record, created, error

    def get_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        student_id: Optional[int] = None,
        class_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 25,
        accessible_class_ids: Optional[List[int]] = None,
    ):
        """
        Paginated, filterable attendance history for the History/Search pages.

        Args:
            accessible_class_ids: If not None, restricts results to these
                ClassRoom IDs — used to enforce a teacher's class restriction.
        """
        stmt = Attendance.query.join(Student)

        if accessible_class_ids is not None:
            if len(accessible_class_ids) == 0:
                stmt = stmt.filter(db.false())
            else:
                stmt = stmt.filter(Attendance.class_id.in_(accessible_class_ids))

        if start_date:
            stmt = stmt.filter(Attendance.attendance_date >= start_date)
        if end_date:
            stmt = stmt.filter(Attendance.attendance_date <= end_date)
        if student_id:
            stmt = stmt.filter(Attendance.student_id == student_id)
        if class_id:
            stmt = stmt.filter(Attendance.class_id == class_id)
        if subject_id:
            stmt = stmt.filter(Attendance.subject_id == subject_id)
        if status:
            stmt = stmt.filter(Attendance.status == status)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.filter(db.or_(Student.name.ilike(like), Student.roll_number.ilike(like)))

        stmt = stmt.order_by(Attendance.attendance_date.desc(), Attendance.time_in.desc())
        return stmt.paginate(page=page, per_page=per_page, error_out=False)

    def get_today_summary(self, class_id: Optional[int] = None, accessible_class_ids: Optional[List[int]] = None) -> Dict[str, int]:
        """Quick stats for the dashboard: total students vs present today."""
        today = date.today()

        student_stmt = Student.query.filter_by(is_active=True)
        present_stmt = Attendance.query.filter(Attendance.attendance_date == today)

        if accessible_class_ids is not None:
            if len(accessible_class_ids) == 0:
                student_stmt = student_stmt.filter(db.false())
                present_stmt = present_stmt.filter(db.false())
            else:
                student_stmt = student_stmt.filter(Student.class_id.in_(accessible_class_ids))
                present_stmt = present_stmt.filter(Attendance.class_id.in_(accessible_class_ids))

        if class_id:
            student_stmt = student_stmt.filter_by(class_id=class_id)
            present_stmt = present_stmt.filter(Attendance.class_id == class_id)

        total_students = student_stmt.count()
        present_count = present_stmt.distinct(Attendance.student_id).count()

        absent_count = max(total_students - present_count, 0)
        percentage = round((present_count / total_students) * 100, 1) if total_students else 0.0

        return {
            "total_students": total_students,
            "present_today": present_count,
            "absent_today": absent_count,
            "attendance_percentage": percentage,
        }

    def get_weekly_trend(self, days: int = 7, accessible_class_ids: Optional[List[int]] = None) -> List[Dict]:
        """Return present-count per day for the last N days (for Chart.js line chart)."""
        from datetime import timedelta

        results = []
        today = date.today()
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            stmt = Attendance.query.filter(Attendance.attendance_date == day)
            if accessible_class_ids is not None:
                if len(accessible_class_ids) == 0:
                    stmt = stmt.filter(db.false())
                else:
                    stmt = stmt.filter(Attendance.class_id.in_(accessible_class_ids))
            count = stmt.distinct(Attendance.student_id).count()
            results.append({"date": day.isoformat(), "count": count})
        return results

    @staticmethod
    def _log(action: str, description: str, level: str = LogLevel.INFO) -> None:
        try:
            db.session.add(SystemLog(actor="system", action=action, description=description, level=level))
            db.session.commit()
        except Exception:  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to write system log for action=%s", action)
