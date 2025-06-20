from django.contrib import admin
from .models import Video, Question, Answer, VideoProgress

admin.site.register(Video)
admin.site.register(Question)
admin.site.register(Answer)
admin.site.register(VideoProgress)
