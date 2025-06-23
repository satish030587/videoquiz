from django.db import models
from django.contrib.auth.models import User
from ckeditor.fields import RichTextField  # for rich text editor

VIDEO_STATUS = (
    ('draft', 'Draft'),
    ('published', 'Published'),
)

LANGUAGES = (
    ('en', 'English'),
    ('hi', 'Hindi'),
    ('es', 'Spanish'),
)

class Video(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    video_file = models.FileField(upload_to='videos/')
    order = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)  # soft delete
    status = models.CharField(max_length=10, choices=VIDEO_STATUS, default='draft')
    quiz_timer_seconds = models.PositiveIntegerField(default=60)

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Video.objects.count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order}. {self.title}"

class Question(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    text_raw = models.TextField(verbose_name="Plain Question Text", null=True, blank=True)
    text_html = RichTextField(verbose_name="Formatted HTML Text", blank=True)
    order = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    language = models.CharField(max_length=5, choices=LANGUAGES, default='en')

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Question.objects.filter(video=self.video).count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.order} - {self.text_raw[:50]}..."

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Answer.objects.filter(question=self.question).count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.text} ({'✔' if self.is_correct else '✘'})"

class VideoProgress(models.Model):
    STATUS_CHOICES = [
        ('not_attempted', 'Not Attempted'),
        ('passed',        'Passed'),
        ('failed',        'Failed'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    video      = models.ForeignKey(Video, on_delete=models.CASCADE)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_attempted')  # ← here
    score      = models.FloatField(null=True, blank=True)
    percentage = models.FloatField(default=0.0)
    passed     = models.BooleanField(default=False)
    attempt_time = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)  # Store user's answers as a JSON object
    time_taken = models.PositiveIntegerField(default=0)  # Time taken in seconds
    completed  = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.video.title} - {'Passed' if self.passed else 'Failed'}"
    
class certificate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    issue_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='certificates/', null=True, blank=True)

    def __str__(self):
        return f"Certificate for {self.user.username} issued on {self.issue_date.strftime('%Y-%m-%d')}"
    