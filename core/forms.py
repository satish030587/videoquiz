from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Video, Question, Answer, VideoProgress
import csv
import io

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
        return user

class QuizAnswerForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        
        # Get answers for this question
        answers = Answer.objects.filter(question=question).order_by('order')
        
        # Create choices for the form field
        choices = [(answer.id, answer.text) for answer in answers]
        
        # Determine field type based on question type
        if question.question_type == 'true_false':
            self.fields['answer'] = forms.ChoiceField(
                choices=[('true', 'True'), ('false', 'False')],
                widget=forms.RadioSelect,
                required=True
            )
        elif question.question_type == 'single_choice':
            self.fields['answer'] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect,
                required=True
            )
        else:  # multiple_choice
            self.fields['answer'] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect,
                required=True
            )

class BulkQuestionImportForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file with questions and answers. See template for format.'
    )
    video = forms.ModelChoiceField(
        queryset=Video.objects.filter(is_active=True),
        label='Video',
        help_text='Select the video for these questions'
    )
    
    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('File must be a CSV file.')
        
        # Read and validate CSV structure
        file.seek(0)
        content = file.read().decode('utf-8')
        csv_data = csv.reader(io.StringIO(content))
        
        headers = next(csv_data, None)
        expected_headers = [
            'question_text', 'question_type', 
            'answer_1', 'answer_1_correct',
            'answer_2', 'answer_2_correct', 
            'answer_3', 'answer_3_correct',
            'answer_4', 'answer_4_correct'
        ]
        
        if not headers or not all(h in headers for h in expected_headers[:2]):
            raise forms.ValidationError(
                f'CSV must contain these headers: {", ".join(expected_headers)}'
            )
        
        file.seek(0)
        return file

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = '__all__'
        widgets = {
            'text_raw': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'explanation': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'hint': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
        }

class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
        }

class AnswerInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        
        correct_answers = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                if form.cleaned_data.get('is_correct'):
                    correct_answers += 1
        
        if correct_answers == 0:
            raise forms.ValidationError('At least one answer must be marked as correct.')
        
        question_type = self.instance.question_type if hasattr(self.instance, 'question_type') else 'multiple_choice'
        if question_type == 'single_choice' and correct_answers > 1:
            raise forms.ValidationError('Single choice questions can only have one correct answer.')

class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)