from django.contrib.auth import authenticate, login, logout
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

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'core/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
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
    video_progress = {vp.video_id: vp for vp in VideoProgress.objects.filter(user=user)}

    video_data = []
    allow_next = True
    for video in videos:
        vp = video_progress.get(video.id)
        if vp:
            status = vp.status             # 'passed', 'failed', or 'not_attempted'
            # Add score and percentage if available
            score = getattr(vp, 'score', None)
            percentage = getattr(vp, 'percentage', None)
        else:
            status = 'not_attempted' if allow_next else 'locked'

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
        'passed': sum(1 for vp in video_progress.values() if vp.status == 'passed'),
        'failed': sum(1 for vp in video_progress.values() if vp.status == 'failed'),
        'not_attempted': videos.count() - len(video_progress),
    }

    return render(request, 'core/dashboard.html', {
        'video_data': video_data,
        'stats': stats,
        'user': user,
    })


@login_required
def quiz_view(request, video_id):
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
        if selected_answer and question_id:
            progress.answers[str(question_id)] = int(selected_answer)
            progress.save()

        # If submit button pressed
        if 'submit-btn' in request.POST:
            unanswered = []
            for q in questions:
                if str(q.id) not in progress.answers:
                    unanswered.append(q.order)
            if unanswered:
                messages.error(request, f"Please answer all questions. Unanswered: {', '.join(map(str, unanswered))}")
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

                # Prepare result details
                result_details = []
                for q in questions:
                    user_ans_id = progress.answers.get(str(q.id))
                    user_answer = Answer.objects.filter(id=user_ans_id, question=q).first() if user_ans_id else None
                    correct_answers = Answer.objects.filter(question=q, is_correct=True)
                    result_details.append({
                        'question': q,
                        'user_answer': user_answer,
                        'correct_answers': correct_answers,
                        'is_correct': user_answer in correct_answers if user_answer else False,
                    })

                return render(request, 'core/quiz_result.html', {
                    'video': video,
                    'score': score,
                    'percentage': percentage,
                    'status': progress.status,
                    'result_details': result_details,
                })

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

            # Prepare result details
            result_details = []
            for q in questions:
                user_ans_id = progress.answers.get(str(q.id))
                user_answer = Answer.objects.filter(id=user_ans_id, question=q).first() if user_ans_id else None
                correct_answers = Answer.objects.filter(question=q, is_correct=True)
                result_details.append({
                    'question': q,
                    'user_answer': user_answer,
                    'correct_answers': correct_answers,
                    'is_correct': user_answer in correct_answers if user_answer else False,
                })

            return render(request, 'core/quiz_result.html', {
                'video': video,
                'score': score,
                'percentage': percentage,
                'status': progress.status,
                'result_details': result_details,
            })

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
    progresses = VideoProgress.objects.filter(user=user, video__in=videos)
    if progresses.count() != videos.count() or any(vp.status != 'passed' for vp in progresses):
        messages.error(request, "You must pass all quizzes to download the certificate.")
    return redirect('dashboard')

    # Generate a simple PDF certificate (you can customize this)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    p.setFont("Helvetica-Bold", 20)
    p.drawString(100, 750, "Certificate of Completion")
    p.setFont("Helvetica", 14)
    p.drawString(100, 700, f"This certifies that {user.get_full_name() or user.username}")
    p.drawString(100, 680, "has successfully completed all video quizzes.")
    p.drawString(100, 660, f"Date: {timezone.now().strftime('%Y-%m-%d')}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="certificate.pdf"'
    })

@login_required
def submit_quiz_view(request, video_id):
    # You can implement this if needed, or just redirect for now
    return redirect('dashboard')