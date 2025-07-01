from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.response import TemplateResponse
import csv, logging, openpyxl
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
    list_display = ['question_text_short', 'video', 'question_type', 'is_active']
    list_filter = ['video', 'question_type', 'is_active', 'language']
    search_fields = ['text_raw', 'video__title']
    ordering = ['video', 'order']
    
    def question_text_short(self, obj):
        return obj.text_raw[:50] + '...' if len(obj.text_raw) > 50 else obj.text_raw
    question_text_short.short_description = 'Question'

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    form = VideoForm
    list_display = ['title', 'quiz_timer_seconds', 'max_attempts', 'passing_score', 'question_count', 'bulk_import_link', 'is_active', 'status']
    list_filter = ['is_active', 'status', 'created_at']
    search_fields = ['title', 'description']
    ordering = ['order']
    change_list_template = "admin/core/video/video_changelist.html"

    def bulk_import_link(self, obj):
        from django.urls import reverse
        if obj.pk:
            url = reverse("admin:core_video_bulk_import_questions", args=[obj.pk])
            return format_html('<a href="{}">Bulk Import Questions</a>', url)
        return "-"
    bulk_import_link.short_description = "Bulk Import"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:object_id>/bulk-import-questions/',
                self.admin_site.admin_view(self.bulk_import_questions),
                name='core_video_bulk_import_questions'
            ),
            path(
            'download-question-template/',
            self.admin_site.admin_view(self.download_template),
            name='core_video_download_question_template'
            ),
        ]
        return custom + urls

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'

    def bulk_import_questions(self, request, object_id):
        video = self.get_object(request, object_id)
        if request.method == 'POST':
            form = BulkQuestionImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = form.cleaned_data['csv_file']
                try:
                    count = self.process_csv_import(csv_file, video)
                    messages.success(request, f"Imported {count} questions successfully.")
                    return redirect(reverse('admin:core_video_change', args=[object_id]))
                except ValueError as e:
                    messages.error(request, str(e))
            else:
                messages.error(request, form.errors.as_ul())
        else:
            form = BulkQuestionImportForm()

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'form': form,
            'video': video,
        }
        return TemplateResponse(
            request,
            "admin/core/video/bulk_import_questions.html",
            context
        )

    def process_csv_import(self, csv_file, video):
        csv_file.seek(0)
        content = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        required_headers = [
            'question_text', 'question_type', 'answer_1','answer_1_correct', 'answer_2', 'answer_2_correct', 'answer_3', 'answer_3_correct', 'answer_4', 'answer_4_correct',
        ]
        print("DEBUG: CSV headers:", reader.fieldnames)
        if reader.fieldnames != required_headers:
            raise ValueError(
                "CSV must contain these headers: " + ", ".join(required_headers)
            )

        created = 0
        for row in reader:
            q = Question.objects.create(
                video=video,
                text_raw=row['question_text'].strip(),
                question_type=row['question_type'].strip(),
                order=Question.objects.filter(video=video).count() + 1
            )
            for i in range(1,5):
                text = row[f'answer_{i}'].strip()
                is_corr = str(row[f'answer_{i}_correct']).strip().lower() in ['true','1','yes']
                Answer.objects.create(
                    question=q,
                    text=text,
                    is_correct=is_corr,
                    order=i
                )
            created += 1

        return created

    def download_template(self, request):
        header = [
            'question_text','question_type',
            'answer_1','answer_1_correct',
            'answer_2','answer_2_correct',
            'answer_3','answer_3_correct',
            'answer_4','answer_4_correct',
        ]
        example = [
            'What is 2+2?', 'multiple_choice',
            '3', 'False',
            '4', 'True',
            '5', 'False',
            '6', 'False',
        ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerow(example)
        content = output.getvalue()
        output.close()
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="question_template.csv"'
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