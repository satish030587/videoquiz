from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.response import TemplateResponse
import csv
import io
from .models import Video, Question, Answer, VideoProgress, Certificate
from .forms import BulkQuestionImportForm, QuestionForm, AnswerInlineFormSet, VideoForm

class AnswerInline(admin.TabularInline):
    model = Answer
    formset = AnswerInlineFormSet
    extra = 4
    max_num = 4  # Limit to 4 answers
    fields = ['text', 'is_correct', 'order']
    ordering = ['order']

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    inlines = [AnswerInline]
    list_display = ['question_text_short', 'video', 'question_type', 'difficulty', 'points', 'is_active']
    list_filter = ['video', 'question_type', 'difficulty', 'is_active', 'language']
    search_fields = ['text_raw', 'video__title']
    ordering = ['video', 'order']
    
    def question_text_short(self, obj):
        return obj.text_raw[:50] + '...' if len(obj.text_raw) > 50 else obj.text_raw
    question_text_short.short_description = 'Question'

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    form = VideoForm
    list_display = ['title', 'quiz_timer_seconds', 'max_attempts', 'passing_score', 'question_count', 'is_active', 'status']
    list_filter = ['is_active', 'status', 'created_at']
    search_fields = ['title', 'description']
    ordering = ['order']
    
    change_list_template = "admin/video_changelist.html"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-import-questions/', self.bulk_import_questions, name='bulk-import-questions'),
            path('download-template/', self.download_template, name='download-question-template'),
        ]
        return custom_urls + urls
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'
    
    def bulk_import_questions(self, request):
        if request.method == 'POST':
            form = BulkQuestionImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = form.cleaned_data['csv_file']
                video = form.cleaned_data['video']
                
                # Process CSV
                try:
                    success_count = self.process_csv_import(csv_file, video)
                    messages.success(request, f'Successfully imported {success_count} questions.')
                    return redirect('..')
                except Exception as e:
                    messages.error(request, f'Error importing questions: {str(e)}')
        else:
            form = BulkQuestionImportForm()
        
        context = {
            'form': form,
            'title': 'Bulk Import Questions',
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/bulk_import_questions.html', context)
    
    def process_csv_import(self, csv_file, video):
        csv_file.seek(0)
        content = csv_file.read().decode('utf-8')
        csv_data = csv.DictReader(io.StringIO(content))
        
        success_count = 0
        for row in csv_data:
            # Create question with default values for removed fields
            question = Question.objects.create(
                video=video,
                text_raw=row['question_text'],
                question_type=row.get('question_type', 'multiple_choice'),
                difficulty='medium',  # Default value
                points=1,  # Default value
                explanation='',  # Default empty
                hint='',  # Default empty
                order=success_count + 1
            )
            
            # Create answers (only 4 answers)
            for i in range(1, 5):  # Only 4 answers: answer_1 to answer_4
                answer_text = row.get(f'answer_{i}', '')
                if answer_text:
                    is_correct = row.get(f'answer_{i}_correct', '').lower() in ['true', '1', 'yes']
                    Answer.objects.create(
                        question=question,
                        text=answer_text,
                        is_correct=is_correct,
                        order=i
                    )
            
            success_count += 1
        
        return success_count
    
    def download_template(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="question_template.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'question_text', 'question_type',
            'answer_1', 'answer_1_correct',
            'answer_2', 'answer_2_correct', 
            'answer_3', 'answer_3_correct',
            'answer_4', 'answer_4_correct'
        ])
        
        # Add sample data
        writer.writerow([
            'What is Django?', 'multiple_choice',
            'A web framework', 'true', 
            'A database', 'false',
            'A programming language', 'false', 
            'An IDE', 'false'
        ])
        
        writer.writerow([
            'Is Python an interpreted language?', 'true_false',
            'True', 'true', 
            'False', 'false',
            '', '', 
            '', ''
        ])
        
        return response

@admin.register(VideoProgress)
class VideoProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'video', 'attempts', 'best_score', 'status', 'passed', 'last_attempt']
    list_filter = ['status', 'passed', 'video', 'last_attempt']
    search_fields = ['user__username', 'video__title']
    readonly_fields = ['last_attempt', 'attempt_time']

@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['user', 'issue_date', 'file']
    list_filter = ['issue_date']
    search_fields = ['user__username']
    readonly_fields = ['issue_date']