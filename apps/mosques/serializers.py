"""سریالایزرهای ورودی و خروجی برای مدیریت مساجد و نمایش رنکینگ مشارکت."""

from __future__ import annotations

from rest_framework import serializers

from .models import Mosque


class MosqueDropdownSerializer(serializers.Serializer):
    """ساختار خروجی آیتم‌های لیست کشویی مساجد در فرم ثبت‌نام."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    neighborhood = serializers.CharField()
    display_order = serializers.IntegerField()
    completed_participants_count = serializers.IntegerField()


class MosqueLeaderboardItemSerializer(serializers.Serializer):
    """ساختار خروجی هر مسجد در جدول رنکینگ لحظه‌ای مشارکت."""

    rank = serializers.IntegerField()
    tier = serializers.CharField()
    tier_label = serializers.CharField()
    mosque_id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    neighborhood = serializers.CharField()
    imam_name = serializers.CharField()
    commander_name = serializers.CharField()
    completed_participants_count = serializers.IntegerField()
    registered_users_count = serializers.IntegerField()
    target_participants = serializers.IntegerField()
    target_progress_percent = serializers.FloatField()
    participation_share_percent = serializers.FloatField()
    average_score = serializers.FloatField()
    average_correct_answers = serializers.FloatField()
    average_duration_seconds = serializers.FloatField()


class MosqueLeaderboardSnapshotSerializer(serializers.Serializer):
    """ساختار کامل پاسخ رنکینگ لحظه‌ای مساجد حوزه ۱۸۵ شهید کاوه."""

    organizer = serializers.CharField()
    total_mosques = serializers.IntegerField()
    total_completed_participants = serializers.IntegerField()
    total_registered_users = serializers.IntegerField()
    leaderboard = MosqueLeaderboardItemSerializer(many=True)


class AdminMosqueSerializer(serializers.ModelSerializer):
    """سریالایزر کامل مسجد برای پنل مدیریت ادمین."""

    class Meta:
        model = Mosque
        fields = [
            "id",
            "code",
            "name",
            "neighborhood",
            "address",
            "imam_name",
            "commander_name",
            "contact_phone",
            "target_participants",
            "display_order",
            "registered_count",
            "completed_exam_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "registered_count",
            "completed_exam_count",
            "created_at",
            "updated_at",
        ]
        extra_kwargs: dict[str, dict[str, list[object]]] = {
            "code": {"validators": []},
            "name": {"validators": []},
        }
