from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Pulls in all the routes from your app's urls.py file
    path('', include('meetings.urls')), 
]