from django.urls import path

from .views import ConversationMessagesView


urlpatterns = [
    path('chat/messages/', ConversationMessagesView.as_view(), name='chat-messages'),
]
