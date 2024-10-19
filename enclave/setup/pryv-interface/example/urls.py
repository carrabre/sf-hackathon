from django.urls import path
from . import views

urlpatterns = [
    path('', views.homepage_view, name='homepage'),
    path('chat/', views.chat_view, name='chat'),
    path('api/query/', views.handle_query, name='handle_query'),
    path('stream_query/', views.stream_query, name='stream_query'),
    path('process-audio/', views.process_audio, name='process_audio'),
]