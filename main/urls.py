from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication
    path('api/auth/', include('skillmatch.urls')),

    # Profile feature
    path('api/', include('skillmatch.profile_urls')),

    # Meetings feature
    path('', include('meetings.urls')),
]


