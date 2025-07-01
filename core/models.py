from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

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
    status = models.CharField(max_length=10, choices=VIDEO_STATUS, default='draft')
    quiz_timer_seconds = models.PositiveIntegerField(default=60)
    # New fields for enhanced functionality
    max_attempts = models.IntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(5)])
    passing_score = models.IntegerField(default=60, validators=[MinValueValidator(1), MaxValueValidator(100)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Video.objects.count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order}. {self.title}"

    class Meta:
        ordering = ['order']

class Question(models.Model):
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('single_choice', 'Single Choice'),
    ]
    
    DIFFICULTY_LEVELS = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='questions')
    text_raw = models.TextField(verbose_name="Plain Question Text", null=True, blank=True)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='multiple_choice')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default='medium')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    language = models.CharField(max_length=5, choices=LANGUAGES, default='en')

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Question.objects.filter(video=self.video).count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.order} - {self.text_raw[:50]}..."

    class Meta:
        ordering = ['order']

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.order == 0:
            self.order = Answer.objects.filter(question=self.question).count() + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.text} ({'✔' if self.is_correct else '✘'})"

    class Meta:
        ordering = ['order']

class VideoProgress(models.Model):
    STATUS_CHOICES = [
        ('not_attempted', 'Not Attempted'),
        ('passed',        'Passed'),
        ('failed',        'Failed'),
        ('in_progress',   'In Progress'),
        ('submitted',     'Submitted'),
        ('timeout',       'Timeout'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_attempted')
    score = models.FloatField(null=True, blank=True)
    percentage = models.FloatField(default=0.0)
    passed = models.BooleanField(default=False)
    attempt_time = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)  # Store user's answers as a JSON object
    time_taken = models.PositiveIntegerField(default=0)  # Time taken in seconds
    completed = models.BooleanField(default=False)
    # New field for attempt tracking
    attempts = models.IntegerField(default=0)
    best_score = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.video.title} - {'Passed' if self.passed else 'Failed'}"

    class Meta:
        unique_together = ['user', 'video']

class Certificate(models.Model):  # Fixed capitalization
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    issue_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='certificates/', null=True, blank=True)

    def __str__(self):
        return f"Certificate for {self.user.username} issued on {self.issue_date.strftime('%Y-%m-%d')}"