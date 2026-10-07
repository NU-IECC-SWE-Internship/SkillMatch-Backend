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
from .quiz_bank import current_cycle


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "is_approved", "created_by", "created_at"]
    list_filter = ["is_approved"]
    search_fields = ["name"]


@admin.register(SkillQuizQuestion)
class SkillQuizQuestionAdmin(admin.ModelAdmin):
    list_display = ["skill", "cycle", "difficulty", "question_text", "correct_option", "created_at"]
    list_filter = ["cycle", "difficulty", "skill"]
    search_fields = ["question_text"]
    ordering = ["skill__name", "-cycle", "id"]

    def get_changeform_initial_data(self, request):
        return {"cycle": current_cycle(), **super().get_changeform_initial_data(request)}


@admin.register(SkillQuizAttempt)
class SkillQuizAttemptAdmin(admin.ModelAdmin):
    list_display = ["user", "skill", "score", "passed", "abandoned", "created_at"]
    list_filter = ["passed", "abandoned", "skill"]


@admin.register(PendingSkillQuiz)
class PendingSkillQuizAdmin(admin.ModelAdmin):
    list_display = ["user", "skill", "created_at"]


admin.site.register(Profile)
admin.site.register(UserSkill)
admin.site.register(AvailabilitySlot)
