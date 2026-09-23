from django.contrib import admin

from .models import (
    Profile,
    Skill,
    UserSkill,
    SkillQuizQuestion,
    SkillQuizAttempt,
    PendingSkillQuiz,
    AvailabilitySlot,
)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(SkillQuizQuestion)
class SkillQuizQuestionAdmin(admin.ModelAdmin):
    list_display = ["skill", "order", "question_text", "correct_option"]
    list_filter = ["skill"]
    ordering = ["skill__name", "order"]


@admin.register(SkillQuizAttempt)
class SkillQuizAttemptAdmin(admin.ModelAdmin):
    list_display = ["user", "skill", "score", "passed", "created_at"]
    list_filter = ["passed", "skill"]


@admin.register(PendingSkillQuiz)
class PendingSkillQuizAdmin(admin.ModelAdmin):
    list_display = ["user", "skill", "created_at"]


admin.site.register(Profile)
admin.site.register(UserSkill)
admin.site.register(AvailabilitySlot)
