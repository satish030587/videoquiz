from django.contrib.auth import authenticate, login, logout
from django.contrib.messages import get_messages
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm
from .models import Video, Question, Answer, VideoProgress
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from .forms import QuizAnswerForm
from django.contrib import messages
from reportlab.pdfgen import canvas
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors

def register_view(request):
    if request.method == 'GET':
        list(get_messages(request))  # Clear any old messages
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration successful! You can now log in.")
            return redirect('login')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = RegisterForm()
    return render(request, 'core/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'GET':
        list(get_messages(request))  # Clear any old messages
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'core/login.html', {'error': 'Invalid credentials'})
    return render(request, 'core/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    user = request.user
    videos = Video.objects.all().order_by('order')
    video_progress = VideoProgress.objects.filter(user=user, video__in=videos)

    all_passed = video_progress.count() == videos.count() and all(vp.status == 'passed' for vp in video_progress)

    video_data = []
    allow_next = True
    for video in videos:
        vp = video_progress.filter(video=video).first()
        if vp:
            status = vp.status             # 'passed', 'failed', or 'not_attempted'
            # Add score and percentage if available
            score = getattr(vp, 'score', None)
            percentage = getattr(vp, 'percentage', None)
        else:
            status = 'not_attempted' if allow_next else 'locked'
            score = None
            percentage = None

        can_start = (status == 'not_attempted') and allow_next

        video_data.append({
            'video': video,
            'status': status,
            'can_start': can_start,
            'score': score if status in ['passed', 'failed'] else None,
            'percentage': percentage if status in ['passed', 'failed'] else None,
        })

        if status != 'passed':
            allow_next = False

    stats = {
        'total': videos.count(),
        'passed': video_progress.filter(status='passed').count(),
        'failed': video_progress.filter(status='failed').count(),
        'not_attempted': videos.count() - video_progress.count(),
    }

    return render(request, 'core/dashboard.html', {
        'video_data': video_data,
        'stats': stats,
        'user': user,
        'all_passed': all_passed,    })


@login_required
def quiz_view(request, video_id):
    if request.method == 'GET':
        # Clear any old messages
        list(get_messages(request))
    user = request.user
    video = get_object_or_404(Video, id=video_id)
    progress, created = VideoProgress.objects.get_or_create(user=user, video=video)
    videos = list(Video.objects.all().order_by('order'))
    current_index = videos.index(video) + 1
    total_videos = len(videos)

    questions = Question.objects.filter(video=video).order_by('order')
    q_index = int(request.GET.get('q', 1)) - 1  # Convert to zero-based index
    if q_index < 0:
        q_index = 0  # Stay on the first question
    if q_index >= questions.count():
        return redirect('dashboard')

    question = questions[q_index]
    answers = Answer.objects.filter(question=question).order_by('order')

    # Security: Prevent retake
    if progress.status in ['passed', 'failed']:
        messages.error(request, "You have already attempted this quiz.")
        return redirect('dashboard')

    # Timer Logic
    if not progress.started_at:
        progress.started_at = timezone.now()
        progress.save()
    time_limit = video.quiz_timer_seconds
    elapsed = (timezone.now() - progress.started_at).total_seconds()
    remaining = max(0, time_limit - int(elapsed))

    # Handle answer saving and navigation
    if request.method == 'POST':
        selected_answer = request.POST.get('selected_answer')
        question_id = request.POST.get('question_id')
        if question_id:
            if selected_answer:
                progress.answers[str(question_id)] = int(selected_answer)
        else:
            progress.answers.pop(str(question_id), None)
        progress.save()

        # If submit button pressed
        if 'submit-btn' in request.POST:
            unanswered = []
            for q in questions:
                if str(q.id) not in progress.answers:
                    unanswered.append(q.order)
            if unanswered:
                messages.error(request, f"Please answer all questions. Unanswered: {', '.join(map(str, unanswered))}")
                question = questions[q_index]
                answers = Answer.objects.filter(question=question).order_by('order')
                return render(request, 'core/quiz.html', {
                    'video': video,
                    'video_position': current_index,
                    'progress': progress,
                    'remaining': remaining,
                    'video_total': total_videos,
                    'question': question,
                    'answers': answers,
                    'q_index': q_index,
                    'total_questions': questions.count(),
                    'prev_index': q_index - 1 if q_index > 0 else None,
                    'next_index': q_index + 1 if q_index < questions.count() - 1 else None,
                })
            else:
                # Grade quiz
                correct = 0
                for q in questions:
                    user_ans_id = progress.answers.get(str(q.id))
                    if user_ans_id and Answer.objects.filter(id=user_ans_id, question=q, is_correct=True).exists():
                        correct += 1
                score = correct
                percentage = (score / len(questions)) * 100
                progress.score = score
                progress.percentage = percentage
                progress.ended_at = timezone.now()
                progress.status = 'passed' if percentage >= 60 else 'failed'
                progress.save()

                # Unlock next video if passed, block others if failed
                if progress.status == 'passed':
                    next_video = Video.objects.filter(order=video.order + 1).first()
                    if next_video:
                        VideoProgress.objects.get_or_create(user=user, video=next_video)
                else:
                    VideoProgress.objects.filter(user=user, video__order__gt=video.order).update(status='failed')

                return redirect('quiz_result', video_id=video.id)

        # If timer expired, auto-submit and show result
        if remaining <= 0:
            # Grade quiz on timeout
            correct = 0
            for q in questions:
                user_ans_id = progress.answers.get(str(q.id))
                if user_ans_id and Answer.objects.filter(id=user_ans_id, question=q, is_correct=True).exists():
                    correct += 1
            score = correct
            percentage = (score / len(questions)) * 100
            progress.score = score
            progress.percentage = percentage
            progress.ended_at = timezone.now()
            progress.status = 'passed' if percentage >= 60 else 'failed'
            progress.save()

            # Unlock next video if passed, block others if failed
            if progress.status == 'passed':
                next_video = Video.objects.filter(order=video.order + 1).first()
                if next_video:
                    VideoProgress.objects.get_or_create(user=user, video=next_video)
            else:
                VideoProgress.objects.filter(user=user, video__order__gt=video.order).update(status='failed')

            return redirect('quiz_result', video_id=video.id)

        # If Next/Previous, redirect to next/prev question
        if 'next-btn' in request.POST:
            return redirect(f"{request.path}?q={q_index + 2}")
        if 'prev-btn' in request.POST:
            if q_index > 0:
                return redirect(f"{request.path}?q={q_index}")
            else:
                return redirect(f"{request.path}?q=1")

    # Prepare context for rendering
    question = questions[q_index]
    answers = Answer.objects.filter(question=question).order_by('order')
    return render(request, 'core/quiz.html', {
        'video': video,
        'video_position': current_index,
        'progress': progress,
        'remaining': remaining,
        'video_total': total_videos,
        'question': question,
        'answers': answers,
        'q_index': q_index,
        'total_questions': questions.count(),
        'prev_index': q_index - 1 if q_index > 0 else None,
        'next_index': q_index + 1 if q_index < questions.count() - 1 else None,
    })

@login_required
def certificate_view(request):
    user = request.user
    videos = Video.objects.all().order_by('order')
    video_progress = VideoProgress.objects.filter(user=user, video__in=videos)
    if video_progress.count() != videos.count() or any(vp.status != 'passed' for vp in video_progress):
        messages.error(request, "You must pass all quizzes to download the certificate.")
        return redirect('dashboard')

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Colors
    main_color = colors.HexColor("#2B3A67")  # Deep blue
    accent_color = colors.HexColor("#F7C873")  # Gold/yellow
    name_bg_color = colors.HexColor("#F7C873")
    white = colors.white

    # Border
    p.setStrokeColor(main_color)
    p.setLineWidth(8)
    p.rect(30, 30, width-60, height-60)

    # Header bar
    p.setFillColor(main_color)
    p.rect(30, height-120, width-60, 60, fill=1, stroke=0)

    # Title
    p.setFont("Helvetica-Bold", 32)
    p.setFillColor(white)
    p.drawCentredString(width/2, height-80, "Certificate of Achievement")

    # Subtitle
    p.setFont("Helvetica", 16)
    p.setFillColor(main_color)
    p.drawCentredString(width/2, height-150, "This is to certify that")

    # Name box
    name = user.get_full_name() or user.username
    name_box_width = 400
    name_box_height = 40
    name_box_x = (width - name_box_width) / 2
    name_box_y = height-200
    p.setFillColor(name_bg_color)
    p.roundRect(name_box_x, name_box_y, name_box_width, name_box_height, 10, fill=1, stroke=0)
    p.setFont("Helvetica-Bold", 22)
    p.setFillColor(main_color)
    p.drawCentredString(width/2, name_box_y + name_box_height/2 + 7, name)

    # Statement
    p.setFont("Helvetica", 16)
    p.setFillColor(main_color)
    p.drawCentredString(width/2, name_box_y - 30, "has successfully completed all video quizzes.")

    # Course/Quiz Name (optional)
    # p.setFont("Helvetica-Oblique", 14)
    # p.drawCentredString(width/2, name_box_y - 55, "Video Quiz Program")

    # Decorative line
    p.setStrokeColor(accent_color)
    p.setLineWidth(2)
    p.line(width/2-120, name_box_y - 60, width/2+120, name_box_y - 60)

    # Date and signature
    p.setFont("Helvetica", 12)
    p.setFillColor(main_color)
    p.drawString(80, 100, f"Date: {timezone.now().strftime('%Y-%m-%d')}")
    p.drawRightString(width-80, 100, "Instructor / Organization")

    # Signature line
    p.setStrokeColor(main_color)
    p.setLineWidth(1)
    p.line(width-220, 110, width-80, 110)

    # Optional: Add a logo (uncomment and set path if you have one)
    # p.drawImage("path/to/logo.png", 60, height-110, width=60, height=60, mask='auto')

    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="certificate.pdf"'
    })

@login_required
def submit_quiz_view(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=request.user, video=video)
    if progress.status in ['passed', 'failed', 'submitted', 'timeout']:
        return redirect('quiz_result', video_id=video_id)
    questions = Question.objects.filter(video=video)
    user_answers = progress.answers  # Assuming this is a dict {question_id: answer_id}
    correct_count = 0

    for question in questions:
        user_answer_id = user_answers.get(str(question.id)) or user_answers.get(int(question.id))
        correct_answer = Answer.objects.filter(question=question, is_correct=True).first()
        is_correct = str(correct_answer.id) == str(user_answer_id) if correct_answer else False
        if is_correct:
            correct_count += 1

    percentage = int((correct_count / questions.count()) * 100) if questions.count() else 0

    # Save score and percentage to progress if needed
    progress.score = correct_count
    progress.percentage = percentage
    progress.status = 'passed' if percentage >= 60 else 'failed'
    progress.passed = percentage >= 60
    progress.ended_at = timezone.now()
    progress.save()

    # Redirect to result page
    return redirect('quiz_result', video_id=video_id)

@login_required
def quiz_result_view(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=request.user, video=video)
    questions = Question.objects.filter(video=video)
    user_answers = progress.answers  # dict {question_id: answer_id}
    results = []
    correct_count = 0

    for question in questions:
        user_answer_id = user_answers.get(str(question.id)) or user_answers.get(int(question.id))
        correct_answer = Answer.objects.filter(question=question, is_correct=True).first()
        user_answer = Answer.objects.filter(id=user_answer_id).first() if user_answer_id else None
        is_correct = str(correct_answer.id) == str(user_answer_id) if correct_answer else False
        if is_correct:
            correct_count += 1
        results.append({
            'question': question,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
        })

    percentage = int((correct_count / questions.count()) * 100) if questions.count() else 0

    return render(request, 'core/quiz_result.html', {
        'video': video,
        'results': results,
        'score': correct_count,
        'total': questions.count(),
        'percentage': percentage,
        'status': progress.status,
    })