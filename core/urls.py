from django.urls import path
from . import views
from .views import (
    register_view,
    login_view,
    logout_view,
    dashboard_view,
    quiz_view,
    get_question_data,
)

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/',    login_view,    name='login'),
    path('logout/',   logout_view,   name='logout'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('quiz/<int:video_id>/', quiz_view, name='quiz'),
    path('quiz/<int:video_id>/result/', views.quiz_result_view, name='quiz_result'),
    path('quiz/<int:video_id>/submit/', views.submit_quiz_view, name='submit_quiz'),
    path('quiz/<int:video_id>/retry/', views.retry_quiz_view, name='retry_quiz'),
    path('certificate/', views.certificate_view, name='certificate'),
    path('quiz/<int:video_id>/auto-submit/', views.auto_submit_quiz, name='auto_submit_quiz'),
    path('quiz/<int:video_id>/sync-timer/', views.sync_timer_view, name='sync_timer'),
    path('quiz/<int:video_id>/get-question/', views.get_question_data, name='get_question_data'),
    path('quiz/<int:video_id>/save-answer/', views.save_answer_view, name='save_answer'),
]
