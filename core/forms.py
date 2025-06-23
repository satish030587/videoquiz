from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class QuizAnswerForm(forms.Form):
    question_id = forms.IntegerField(widget=forms.HiddenInput())
    selected_answer = forms.IntegerField(widget=forms.RadioSelect)