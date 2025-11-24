from django.contrib import admin
from django.urls import path
from interviewapp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('start_session/', views.start_interview, name='start_interview'),
    path('interview/', views.interview, name='interview'),
    path('submit_answer/', views.submit_answer, name='submit_answer'),
    path("feedback/<str:session_id>/", views.feedback, name="feedback"),
    path("end_interview/", views.end_interview, name="end_interview"),
]
