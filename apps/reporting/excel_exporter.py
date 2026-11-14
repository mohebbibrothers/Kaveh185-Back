"""موتور تولید گزارش اکسل چندبرگی راست‌به‌چپ (RTL `.xlsx`) برای مراسم قرعه‌کشی حضوری و تحلیل مدیریتی."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.core.jalali import format_jalali_datetime
from apps.exam.models import ExamAttempt

from .selectors import (
    get_live_analytics_dashboard,
    serialize_admin_participant_row,
)

HEADER_FILL = PatternFill(start_color="1B4332", end_color="1B4332", fill_type="solid")
ALT_ROW_FILL = PatternFill(start_color="F4F9F5", end_color="F4F9F5", fill_type="solid")
HEADER_FONT = Font(name="Tahoma", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Tahoma", size=10, bold=False, color="111827")
THIN_BORDER = Border(
    left=Side(style="thin", color="D1D5DB"),
    right=Side(style="thin", color="D1D5DB"),
    top=Side(style="thin", color="D1D5DB"),
    bottom=Side(style="thin", color="D1D5DB"),
)


def _style_worksheet(ws: Any, headers: list[str]) -> None:
    """تنظیم راست‌به‌چپ (RTL)، هدر رنگی، فیلتر خودکار اکسل و فریز سطر اول."""
    ws.views.sheetView[0].rightToLeft = True
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"


def _finalize_worksheet_layout(ws: Any) -> None:
    """اعمال فونت، کادر، رنگ متناوب سطرها، فیلتر خودکار و عرض ستون‌ها."""
    max_row = ws.max_row
    max_col = ws.max_column

    for r_idx in range(2, max_row + 1):
        is_alt = r_idx % 2 == 0
        for c_idx in range(1, max_col + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            if is_alt:
                cell.fill = ALT_ROW_FILL
            cell.alignment = Alignment(horizontal="right", vertical="center")

    if max_row >= 1 and max_col >= 1:
        last_col_letter = get_column_letter(max_col)
        ws.auto_filter.ref = f"A1:{last_col_letter}{max_row}"

    for c_idx in range(1, max_col + 1):
        col_letter = get_column_letter(c_idx)
        max_len = 12
        for r_idx in range(1, min(max_row + 1, 200)):
            val = ws.cell(row=r_idx, column=c_idx).value
            if val is not None:
                max_len = max(max_len, min(len(str(val)) + 4, 48))
        ws.column_dimensions[col_letter].width = max_len


def _age_group_label(age_years: int | None) -> str:
    """برچسب ردهٔ سنی شرکت‌کننده برای شیت تفکیک سنی."""
    if age_years is None:
        return "نامشخص"
    if age_years < 18:
        return "۱. نوجوانان (زیر ۱۸ سال)"
    if age_years <= 25:
        return "۲. جوانان (۱۸ تا ۲۵ سال)"
    if age_years <= 35:
        return "۳. بزرگسالان جوان (۲۶ تا ۳۵ سال)"
    if age_years <= 50:
        return "۴. میان‌سالان (۳۶ تا ۵۰ سال)"
    return "۵. پیشکسوتان (بالای ۵۰ سال)"


def generate_multi_sheet_participants_excel(
    *,
    attempts: list[ExamAttempt],
    applied_filters: dict[str, Any] | None = None,
) -> tuple[bytes, str]:
    """تولید فایل اکسل ۷ برگی راست‌به‌چپ برای قرعه‌کشی حضوری و گزارش جامع مدیریتی."""
    wb = Workbook()
    serialized_rows = [
        serialize_admin_participant_row(att, rank=idx, include_answers=True)
        for idx, att in enumerate(attempts, start=1)
    ]
    analytics = get_live_analytics_dashboard()

    # =========================================================================
    # برگ ۱: رتبه‌بندی قرعه‌کشی (برترین‌ها بر اساس تعداد درست و سرعت)
    # =========================================================================
    ws1 = wb.active
    ws1.title = "رتبه‌بندی قرعه‌کشی (برترین‌ها)"
    headers_sheet1 = [
        "رتبه کل",
        "کد رهگیری قرعه‌کشی",
        "نام",
        "نام خانوادگی",
        "نام و نام خانوادگی",
        "کد ملی",
        "شماره موبایل",
        "تاریخ تولد (شمسی)",
        "سن (سال)",
        "رده سنی",
        "کد مسجد",
        "نام مسجد",
        "محله / پایگاه",
        "تعداد کل سوالات",
        "تعداد پاسخ درست",
        "تعداد پاسخ غلط",
        "تعداد بی‌پاسخ",
        "درصد صحت (%)",
        "زمان صرف‌شده (ثانیه)",
        "زمان صرف‌شده (خوانا)",
        "امتیاز پایه",
        "پاداش سرعت",
        "امتیاز کل نهایی",
        "وضعیت پایان آزمون",
        "زمان ثبت کارنامه (شمسی)",
    ]
    _style_worksheet(ws1, headers_sheet1)

    for row in serialized_rows:
        u = row["user"]
        m = row["mosque"]
        ex = row["exam"]
        ws1.append(
            [
                row["rank"],
                row["tracking_code"],
                u["first_name"],
                u["last_name"],
                u["full_name"],
                u["national_id"],
                u["phone_number"],
                u["birth_date_jalali"],
                u["age_years"],
                _age_group_label(u["age_years"]),
                m["code"] or "",
                m["name"] or "",
                m["neighborhood"] or "",
                ex["total_questions"],
                ex["correct_count"],
                ex["wrong_count"],
                ex["unanswered_count"],
                ex["accuracy_percent"],
                ex["duration_seconds"],
                ex["duration_display"],
                ex["base_score"],
                ex["time_bonus_score"],
                ex["total_score"],
                ex["status_label"],
                ex["completed_at_jalali"],
            ]
        )
    _finalize_worksheet_layout(ws1)

    # =========================================================================
    # برگ ۲: مشخصات کامل و ریز پاسخ‌های ۵ سوال هر شرکت‌کننده
    # =========================================================================
    ws2 = wb.create_sheet(title="مشخصات کامل و ریز پاسخ‌ها")
    headers_sheet2 = [
        "رتبه",
        "کد رهگیری",
        "نام و نام خانوادگی",
        "کد ملی",
        "شماره موبایل",
        "سن",
        "نام مسجد",
        "تعداد درست",
        "تعداد غلط",
        "تعداد بی‌پاسخ",
        "زمان (ثانیه)",
        "امتیاز کل",
    ]
    for q_idx in range(1, 6):
        headers_sheet2.extend(
            [
                f"سوال {q_idx} (متن صورت سوال)",
                f"گزینه انتخابی سوال {q_idx}",
                f"پاسخ صحیح سوال {q_idx}",
                f"نتیجه سوال {q_idx}",
            ]
        )
    _style_worksheet(ws2, headers_sheet2)

    for row in serialized_rows:
        u = row["user"]
        m = row["mosque"]
        ex = row["exam"]
        answers = list(row.get("answers") or [])
        ans_by_num = {int(a["question_number"]): a for a in answers}

        line: list[Any] = [
            row["rank"],
            row["tracking_code"],
            u["full_name"],
            u["national_id"],
            u["phone_number"],
            u["age_years"],
            m["name"] or "",
            ex["correct_count"],
            ex["wrong_count"],
            ex["unanswered_count"],
            ex["duration_seconds"],
            ex["total_score"],
        ]
        for q_idx in range(1, 6):
            ans = ans_by_num.get(q_idx)
            if ans is None:
                line.extend(["—", "—", "—", "—"])
            else:
                line.extend(
                    [
                        ans["question_text"],
                        ans["selected_option_text"] or "بدون پاسخ",
                        ans["correct_option_text"],
                        ans["result_status_label"],
                    ]
                )
        ws2.append(line)
    _finalize_worksheet_layout(ws2)

    # =========================================================================
    # برگ ۳: رتبه‌بندی مشارکت مساجد (۱۷ مسجد حوزه ۱۸۵ شهید کاوه)
    # =========================================================================
    ws3 = wb.create_sheet(title="رتبه‌بندی مشارکت مساجد")
    headers_sheet3 = [
        "رتبه مسجد",
        "کد مسجد",
        "نام مسجد",
        "محله / پایگاه",
        "تعداد شرکت‌کنندگان آزمون‌داده",
        "تعداد کل ثبت‌نام‌کنندگان مسجد",
        "سهم از کل مشارکت (%)",
        "میانگین امتیاز کل مسجد",
        "میانگین پاسخ درست (از ۵)",
        "میانگین زمان پاسخگویی (ثانیه)",
        "تعداد نفرات ۵ از ۵ (نمره کامل)",
    ]
    _style_worksheet(ws3, headers_sheet3)

    for m_stat in analytics["mosques_ranking_and_analytics"]:
        ws3.append(
            [
                m_stat["rank"],
                m_stat["code"],
                m_stat["name"],
                m_stat["neighborhood"],
                m_stat["completed_participants_count"],
                m_stat["registered_participants_count"],
                m_stat["participation_share_percent"],
                m_stat["average_total_score"],
                m_stat["average_correct_count"],
                m_stat["average_duration_seconds"],
                m_stat["perfect_5_of_5_count"],
            ]
        )
    _finalize_worksheet_layout(ws3)

    # =========================================================================
    # برگ ۴: تفکیک و رتبه‌بندی داخلی بر اساس هر مسجد (ویژه قرعه‌کشی مسجدمحور)
    # =========================================================================
    ws4 = wb.create_sheet(title="تفکیک بر اساس مساجد")
    headers_sheet4 = [
        "نام مسجد",
        "رتبه در مسجد",
        "رتبه کل",
        "کد رهگیری",
        "نام و نام خانوادگی",
        "کد ملی",
        "شماره موبایل",
        "تاریخ تولد (شمسی)",
        "سن",
        "پاسخ درست",
        "پاسخ غلط",
        "بی‌پاسخ",
        "زمان (ثانیه)",
        "امتیاز کل",
    ]
    _style_worksheet(ws4, headers_sheet4)

    rows_by_mosque = sorted(
        serialized_rows,
        key=lambda r: (
            str(r["mosque"]["name"] or ""),
            -float(r["exam"]["total_score"]),
            int(r["exam"]["duration_seconds"]),
        ),
    )
    current_mosque_name = None
    mosque_internal_rank = 0
    for row in rows_by_mosque:
        m_name = str(row["mosque"]["name"] or "نامشخص")
        if m_name != current_mosque_name:
            current_mosque_name = m_name
            mosque_internal_rank = 1
        else:
            mosque_internal_rank += 1

        u = row["user"]
        ex = row["exam"]
        ws4.append(
            [
                m_name,
                mosque_internal_rank,
                row["rank"],
                row["tracking_code"],
                u["full_name"],
                u["national_id"],
                u["phone_number"],
                u["birth_date_jalali"],
                u["age_years"],
                ex["correct_count"],
                ex["wrong_count"],
                ex["unanswered_count"],
                ex["duration_seconds"],
                ex["total_score"],
            ]
        )
    _finalize_worksheet_layout(ws4)

    # =========================================================================
    # برگ ۵: تفکیک و رتبه‌بندی بر اساس رده‌های سنی
    # =========================================================================
    ws5 = wb.create_sheet(title="تفکیک رده‌های سنی")
    headers_sheet5 = [
        "رده سنی",
        "رتبه در رده سنی",
        "رتبه کل",
        "کد رهگیری",
        "نام و نام خانوادگی",
        "کد ملی",
        "شماره موبایل",
        "تاریخ تولد (شمسی)",
        "سن (سال)",
        "نام مسجد",
        "پاسخ درست",
        "پاسخ غلط",
        "زمان (ثانیه)",
        "امتیاز کل",
    ]
    _style_worksheet(ws5, headers_sheet5)

    rows_by_age_group = sorted(
        serialized_rows,
        key=lambda r: (
            _age_group_label(r["user"]["age_years"]),
            -float(r["exam"]["total_score"]),
            int(r["exam"]["duration_seconds"]),
        ),
    )
    current_age_group = None
    age_internal_rank = 0
    for row in rows_by_age_group:
        ag_label = _age_group_label(row["user"]["age_years"])
        if ag_label != current_age_group:
            current_age_group = ag_label
            age_internal_rank = 1
        else:
            age_internal_rank += 1

        u = row["user"]
        ex = row["exam"]
        ws5.append(
            [
                ag_label,
                age_internal_rank,
                row["rank"],
                row["tracking_code"],
                u["full_name"],
                u["national_id"],
                u["phone_number"],
                u["birth_date_jalali"],
                u["age_years"],
                row["mosque"]["name"] or "",
                ex["correct_count"],
                ex["wrong_count"],
                ex["duration_seconds"],
                ex["total_score"],
            ]
        )
    _finalize_worksheet_layout(ws5)

    # =========================================================================
    # برگ ۶: تحلیل بانک سوالات
    # =========================================================================
    ws6 = wb.create_sheet(title="تحلیل بانک سوالات")
    headers_sheet6 = [
        "شناسه سوال",
        "متن صورت سوال",
        "فصل / بخش",
        "سطح دشواری",
        "وضعیت فعال",
        "تعداد دفعات قرعه افتادن",
        "تعداد پاسخ درست",
        "تعداد پاسخ غلط",
        "تعداد بی‌پاسخ",
        "درصد پاسخگویی صحیح (%)",
    ]
    _style_worksheet(ws6, headers_sheet6)

    for q_stat in analytics["question_bank_analytics"]:
        ws6.append(
            [
                q_stat["question_id"],
                q_stat["text"],
                q_stat["chapter"],
                q_stat["difficulty"],
                "فعال" if q_stat["is_active"] else "غیرفعال",
                q_stat["times_drawn"],
                q_stat["correct_count"],
                q_stat["wrong_count"],
                q_stat["unanswered_count"],
                q_stat["accuracy_percent"],
            ]
        )
    _finalize_worksheet_layout(ws6)

    # =========================================================================
    # برگ ۷: خلاصه مدیریتی و متادیتای گزارش
    # =========================================================================
    ws7 = wb.create_sheet(title="خلاصه مدیریتی و متادیتا")
    _style_worksheet(ws7, ["شاخص / عنوان", "مقدار"])
    ov = analytics["overview"]
    now = timezone.now()
    summary_pairs = [
        ("عنوان سامانه", "سامانه مسابقه کتابخوانی هفته بسیج — حوزه مقاومت بسیج ۱۸۵ شهید کاوه"),
        ("زمان تولید گزارش (شمسی)", format_jalali_datetime(now)),
        ("زمان تولید گزارش (UTC)", now.isoformat()),
        ("تعداد رکوردهای موجود در این خروجی فیلترشده", len(serialized_rows)),
        ("کل ثبت‌نام‌کنندگان سامانه", ov["total_registered_participants"]),
        ("کل شرکت‌کنندگان آزمون‌داده", ov["total_finished_exams"]),
        ("تعداد نفرات با نمره کامل (۵ از ۵)", ov["perfect_score_5_of_5_count"]),
        ("میانگین پاسخ درست کل سامانه", ov["average_correct_answers"]),
        ("میانگین امتیاز کل سامانه", ov["average_total_score"]),
        ("میانگین زمان پاسخگویی (ثانیه)", ov["average_duration_seconds"]),
        ("فیلترهای اعمال‌شده روی این گزارش", str(applied_filters or {})),
    ]
    for k, v in summary_pairs:
        ws7.append([k, v])
    _finalize_worksheet_layout(ws7)

    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    sha256_hex = hashlib.sha256(content).hexdigest()
    return content, sha256_hex
