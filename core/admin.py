from django.contrib import admin
from .models import Video, Question, Answer, VideoProgress

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 2

class VideoAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]

class QuestionAdmin(admin.ModelAdmin):
    inlines = [AnswerInline]


admin.site.register(Video, VideoAdmin)
admin.site.register(Answer)
admin.site.register(VideoProgress)

class QuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'video', 'language']
    fields = ['video', 'language', 'text_raw', 'text_html', 'order', 'is_deleted']

admin.site.register(Question, QuestionAdmin)