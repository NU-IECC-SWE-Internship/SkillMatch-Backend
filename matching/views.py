from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from skillmatch.models import UserSkill
from .serializers import MatchSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def find_matches(request):
    current_user = request.user

    teach = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="teach"
        ).values_list("skill_id", flat=True)
    )

    learn = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="learn"
        ).values_list("skill_id", flat=True)
    )

    matches = []

    result_users = (
        UserSkill.objects
        .exclude(user=current_user)
        .values_list("user", flat=True)
        .distinct()
    )

    for user_id in result_users:

        their_teach = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="teach"
            ).values_list("skill_id", flat=True)
        )

        their_learn = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="learn"
            ).values_list("skill_id", flat=True)
        )

        teach_me = learn & their_teach
        teach_them = teach & their_learn

        if teach_me and teach_them:
            matches.append({
                "user_id": user_id,
                "username": UserSkill.objects
                    .filter(user_id=user_id)
                    .first()
                    .user.username,
                "teach_me": list(
                    UserSkill.objects
                    .filter(user_id=user_id, skill_id__in=teach_me)
                    .values_list("skill__name", flat=True)
                ),
                "teach_them": list(
                    UserSkill.objects
                    .filter(user_id=user_id, skill_id__in=teach_them)
                    .values_list("skill__name", flat=True)
                ),
            })

    return Response(MatchSerializer(matches, many=True).data)