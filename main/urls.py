from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication
    path('api/auth/', include('skillmatch.urls')),

    # Profile and matching features
    path("api/", include("skillmatch.profile_urls")),
    path("api/", include("matching.urls")),

    # Meetings feature
    path('', include('meetings.urls')),
]


