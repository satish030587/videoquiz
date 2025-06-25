from django.contrib import admin
from .models import Video, Question, Answer, VideoProgress
from django.utils.html import format_html

# Inline answers for Question
class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 2  # show 2 options by default

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

# Customize Answer display
@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('text', 'question', 'is_correct', 'order')
    list_filter = ('is_correct', 'question__video__title')
    search_fields = ('text',)

# Customize Question with inline answers
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    inlines = [AnswerInline]
    list_display = ('text_raw', 'video', 'order', 'language', 'is_deleted')
    list_filter = ('video', 'language', 'is_deleted')
    search_fields = ('text_raw',)

# Customize Video
@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    list_display = ('title', 'order', 'status', 'quiz_timer_seconds', 'is_deleted')
    list_filter = ('status', 'is_deleted')
    search_fields = ('title',)
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'video_file')
        }),
        ('Quiz Settings', {
            'fields': ('quiz_timer_seconds', 'status', 'order', 'is_deleted')
        }),
    )

# Customize Progress Admin
@admin.register(VideoProgress)
class VideoProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'score', 'percentage', 'passed_display', 'attempt_time')
    def passed_display(self, obj):
        if obj.status == 'passed':
            return format_html("<span style='color: green;'>✔️</span>")
        elif obj.status == 'failed':
            return format_html("<span style='color: red;'>❌</span>")
        return '-'
    passed_display.short_description = 'Passed'
    list_filter = ('video', 'passed')
    search_fields = ('user__username', 'video__title')
