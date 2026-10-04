from django.urls import path

from .views import ConversationMessagesView, MarkChatReadView, RecentChatsView


urlpatterns = [
    path('chat/messages/', ConversationMessagesView.as_view(), name='chat-messages'),
    path('chat/recent/', RecentChatsView.as_view(), name='chat-recent'),
    path('chat/<int:user_id>/read/', MarkChatReadView.as_view(), name='chat-mark-read'),
]
