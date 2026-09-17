from rest_framework import serializers


class MatchSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    teach_me = serializers.ListField(
        child=serializers.CharField()
    )
    teach_them = serializers.ListField(
        child=serializers.CharField()
    )