from django.contrib.auth import authenticate, login, logout
from django.contrib.messages import get_messages
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm
from .models import Video, Question, Answer, VideoProgress, Certificate
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
    videos = Video.objects.filter(is_active=True, status='published').order_by('order')
    video_progress = VideoProgress.objects.filter(user=user)

    # Calculate overall statistics
    total_videos = videos.count()
    passed_count = video_progress.filter(status='passed').count()
    failed_count = video_progress.filter(status__in=['failed', 'timeout']).count()
    not_attempted_count = total_videos - video_progress.count()
    
    # Calculate average score and completion percentage
    completed_progress = video_progress.filter(status__in=['passed', 'failed', 'timeout'])
    average_score = 0
    if completed_progress.exists():
        total_percentage = sum([p.percentage for p in completed_progress])
        average_score = total_percentage / completed_progress.count()
    
    completion_percentage = (passed_count / total_videos * 100) if total_videos > 0 else 0
    
    # Calculate total retries remaining
    total_retries_remaining = 0
    for video in videos:
        progress = video_progress.filter(video=video).first()
        if progress:
            retries_left = video.max_attempts - progress.attempts
            total_retries_remaining += max(0, retries_left)
        else:
            total_retries_remaining += video.max_attempts

    # Check if all videos are passed for certificate eligibility
    all_passed = passed_count == total_videos

    # Build video data with status logic
    video_data = []
    for index, video in enumerate(videos):
        progress = video_progress.filter(video=video).first()
        
        # Determine if video is unlocked
        is_unlocked = True
        if index > 0:  # Video 1 is always unlocked
            previous_video = videos[index - 1]
            prev_progress = video_progress.filter(video=previous_video).first()
            is_unlocked = prev_progress and prev_progress.status == 'passed'
        
        # Determine status and button states
        if not is_unlocked:
            status = 'locked'
            can_start = False
            can_retry = False
        elif not progress:
            status = 'not_attempted'
            can_start = True
            can_retry = False
        elif progress.status == 'in_progress':
            status = 'in_progress'
            can_start = True
            can_retry = False
        elif progress.status == 'passed':
            status = 'passed'
            can_start = False
            can_retry = False
        else:  # failed or timeout
            status = 'failed'
            can_start = False
            can_retry = progress.attempts < video.max_attempts
        
        # Calculate attempts and retries
        attempts_used = progress.attempts if progress else 0
        retries_remaining = video.max_attempts - attempts_used
        
        video_data.append({
            'video': video,
            'status': status,
            'is_unlocked': is_unlocked,
            'can_start': can_start,
            'can_retry': can_retry,
            'attempts_used': attempts_used,
            'max_attempts': video.max_attempts,
            'retries_remaining': max(0, retries_remaining),
            'score': progress.score if progress and progress.status in ['passed', 'failed', 'timeout'] else None,
            'percentage': progress.percentage if progress and progress.status in ['passed', 'failed', 'timeout'] else None,
            'best_score': progress.best_score if progress else 0,
        })

    stats = {
        'total_videos': total_videos,
        'passed_count': passed_count,
        'failed_count': failed_count,
        'not_attempted_count': not_attempted_count,
        'total_retries_remaining': total_retries_remaining,
        'average_score': round(average_score, 1),
        'completion_percentage': round(completion_percentage, 1),
    }

    return render(request, 'core/dashboard.html', {
        'video_data': video_data,
        'stats': stats,
        'user': user,
        'all_passed': all_passed,
    })

@login_required
def quiz_view(request, video_id):
    if request.method == 'GET':
        # Clear any old messages
        list(get_messages(request))
    
    user = request.user
    video = get_object_or_404(Video, id=video_id, is_active=True)
    progress, created = VideoProgress.objects.get_or_create(user=user, video=video)

    # Check if user has exceeded max attempts
    if progress.attempts >= video.max_attempts and progress.status != 'passed':
        messages.error(request, f"You have reached the maximum number of attempts ({video.max_attempts}) for this quiz.")
        return redirect('dashboard')
    
    # Check if user has already passed
    if progress.status == 'passed':
        messages.info(request, "You have already passed this quiz.")
        return redirect('quiz_result', video_id=video.id)
    
    videos = list(Video.objects.filter(is_active=True, status='published').order_by('order'))
    current_index = videos.index(video) + 1
    total_videos = len(videos)

    questions = Question.objects.filter(video=video, is_active=True).order_by('order')
    if not questions.exists():
        messages.error(request, "No questions available for this video.")
        return redirect('dashboard')
    
    q_index = int(request.GET.get('q', 1)) - 1  # Convert to zero-based index
    if q_index < 0:
        q_index = 0  # Stay on the first question
    if q_index >= questions.count():
        return redirect('dashboard')

    question = questions[q_index]
    answers = Answer.objects.filter(question=question).order_by('order')

    # Timer Logic - Start new attempt if needed
    if not progress.started_at or progress.status in ['failed', 'timeout']:
        progress.started_at = timezone.now()
        progress.attempts += 1  # Increment attempt count
        progress.status = 'in_progress'
        progress.answers = {}  # Reset answers for new attempt
        progress.save()
    
    time_limit = video.quiz_timer_seconds
    elapsed = (timezone.now() - progress.started_at).total_seconds()
    remaining = max(0, time_limit - int(elapsed))

    # Auto-submit if time expired
    if remaining <= 0:
        return redirect('auto_submit_quiz', video_id=video.id)

    # Handle answer saving and navigation
    if request.method == 'POST':
        selected_answer = request.POST.get('selected_answer')
        question_id = request.POST.get('question_id')
        
        if question_id and selected_answer:
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
                    'attempts_left': video.max_attempts - progress.attempts,
                    'max_attempts': video.max_attempts,
                })
            else:
                # Grade quiz with points system
                correct = 0
                total_points = 0
                earned_points = 0
                
                for q in questions:
                    total_points += q.points
                    user_ans_id = progress.answers.get(str(q.id))
                    if user_ans_id and Answer.objects.filter(id=user_ans_id, question=q, is_correct=True).exists():
                        correct += 1
                        earned_points += q.points
                
                score = correct
                percentage = (earned_points / total_points * 100) if total_points > 0 else 0
                progress.score = score
                progress.percentage = percentage
                progress.ended_at = timezone.now()
                progress.status = 'passed' if percentage >= video.passing_score else 'failed'
                progress.passed = percentage >= video.passing_score
                
                # Update best score
                if percentage > progress.best_score:
                    progress.best_score = int(percentage)
                
                progress.save()

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
        'attempts_left': video.max_attempts - progress.attempts,
        'max_attempts': video.max_attempts,
    })

@login_required
def auto_submit_quiz(request, video_id):
    """Auto-submit quiz when timer expires"""
    user = request.user
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=user, video=video)
    
    if progress.status != 'in_progress':
        return redirect('quiz_result', video_id=video.id)
    
    questions = Question.objects.filter(video=video, is_active=True).order_by('order')
    
    # Grade quiz with points system
    correct = 0
    total_points = 0
    earned_points = 0
    
    for q in questions:
        total_points += q.points
        user_ans_id = progress.answers.get(str(q.id))
        if user_ans_id and Answer.objects.filter(id=user_ans_id, question=q, is_correct=True).exists():
            correct += 1
            earned_points += q.points
    
    score = correct
    percentage = (earned_points / total_points * 100) if total_points > 0 else 0
    progress.score = score
    progress.percentage = percentage
    progress.ended_at = timezone.now()
    progress.status = 'timeout'
    progress.passed = percentage >= video.passing_score
    
    # Update best score
    if percentage > progress.best_score:
        progress.best_score = int(percentage)
    
    progress.save()
    
    messages.warning(request, "Time expired! Quiz has been automatically submitted.")
    return redirect('quiz_result', video_id=video.id)

@login_required
def certificate_view(request):
    user = request.user
    videos = Video.objects.filter(is_active=True, status='published').order_by('order')
    video_progress = VideoProgress.objects.filter(user=user, video__in=videos)
    
    if video_progress.count() != videos.count() or any(vp.status != 'passed' for vp in video_progress):
        messages.error(request, "You must pass all quizzes to download the certificate.")
        return redirect('dashboard')

    # Check if certificate already exists
    certificate, created = Certificate.objects.get_or_create(user=user)

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

    # Course info
    p.setFont("Helvetica-Oblique", 14)
    p.drawCentredString(width/2, name_box_y - 55, f"Completed {videos.count()} video quizzes with passing scores")

    # Decorative line
    p.setStrokeColor(accent_color)
    p.setLineWidth(2)
    p.line(width/2-120, name_box_y - 80, width/2+120, name_box_y - 80)

    # Date and signature
    p.setFont("Helvetica", 12)
    p.setFillColor(main_color)
    p.drawString(80, 100, f"Date: {certificate.issue_date.strftime('%Y-%m-%d')}")
    p.drawRightString(width-80, 100, "Video Quiz Administrator")

    # Signature line
    p.setStrokeColor(main_color)
    p.setLineWidth(1)
    p.line(width-220, 110, width-80, 110)

    # Certificate ID
    p.setFont("Helvetica", 8)
    p.setFillColor(colors.gray)
    p.drawCentredString(width/2, 50, f"Certificate ID: VQ-{user.id}-{certificate.id}")

    p.showPage()
    p.save()
    buffer.seek(0)
    
    return HttpResponse(buffer, content_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="certificate_{user.username}.pdf"'
    })

@login_required
def submit_quiz_view(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=request.user, video=video)
    
    if progress.status in ['passed', 'failed', 'submitted', 'timeout']:
        return redirect('quiz_result', video_id=video_id)
    
    questions = Question.objects.filter(video=video, is_active=True)
    
    # Grade quiz with points system
    correct_count = 0
    total_points = 0
    earned_points = 0

    for question in questions:
        total_points += question.points
        user_answer_id = progress.answers.get(str(question.id))
        if user_answer_id and Answer.objects.filter(id=user_answer_id, question=question, is_correct=True).exists():
            correct_count += 1
            earned_points += question.points

    percentage = (earned_points / total_points * 100) if total_points > 0 else 0

    # Save score and percentage to progress
    progress.score = correct_count
    progress.percentage = percentage
    progress.status = 'passed' if percentage >= video.passing_score else 'failed'
    progress.passed = percentage >= video.passing_score
    progress.ended_at = timezone.now()
    
    # Update best score
    if percentage > progress.best_score:
        progress.best_score = int(percentage)
    
    progress.save()

    # Redirect to result page
    return redirect('quiz_result', video_id=video_id)

@login_required
def quiz_result_view(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=request.user, video=video)
    questions = Question.objects.filter(video=video, is_active=True).order_by('order')
    user_answers = progress.answers  # dict {question_id: answer_id}
    results = []
    correct_count = 0

    for question in questions:
        user_answer_id = user_answers.get(str(question.id))
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
            'points': question.points if is_correct else 0,
        })

    # Check if all videos are passed for certificate eligibility
    all_videos = Video.objects.filter(is_active=True, status='published').order_by('order')
    all_progress = VideoProgress.objects.filter(user=request.user, video__in=all_videos)
    all_passed = all_progress.count() == all_videos.count() and all(vp.status == 'passed' for vp in all_progress)

    return render(request, 'core/quiz_result.html', {
        'video': video,
        'results': results,
        'score': correct_count,
        'total': questions.count(),
        'percentage': progress.percentage,
        'status': progress.status,
        'progress': progress,
        'all_passed': all_passed,
        'attempts_left': video.max_attempts - progress.attempts,
        'max_attempts': video.max_attempts,
    })

@login_required
def video_detail_view(request, video_id):
    """View for displaying video content before quiz"""
    video = get_object_or_404(Video, id=video_id, is_active=True)
    progress, created = VideoProgress.objects.get_or_create(user=request.user, video=video)
    
    # Check if user can access this video (sequential access)
    videos = Video.objects.filter(is_active=True, status='published').order_by('order')
    video_list = list(videos)
    current_index = video_list.index(video)
    
    # Check if previous videos are completed
    can_access = True
    if current_index > 0:
        previous_videos = video_list[:current_index]
        for prev_video in previous_videos:
            prev_progress = VideoProgress.objects.filter(user=request.user, video=prev_video).first()
            if not prev_progress or prev_progress.status != 'passed':
                can_access = False
                break
    
    if not can_access:
        messages.error(request, "You must complete previous videos first.")
        return redirect('dashboard')
    
    return render(request, 'core/video_detail.html', {
        'video': video,
        'progress': progress,
        'can_start_quiz': progress.attempts < video.max_attempts or progress.status == 'passed',
    })

@login_required
def retry_quiz_view(request, video_id):
    """Allow user to retry a failed quiz"""
    video = get_object_or_404(Video, id=video_id)
    progress = VideoProgress.objects.get(user=request.user, video=video)
    
    # Check if retry is allowed
    if progress.attempts >= video.max_attempts:
        messages.error(request, "You have reached the maximum number of attempts for this quiz.")
        return redirect('dashboard')
    
    if progress.status == 'passed':
        messages.info(request, "You have already passed this quiz.")
        return redirect('quiz_result', video_id=video.id)
    
    # Reset progress for retry
    progress.started_at = None
    progress.answers = {}
    progress.status = 'not_attempted'
    progress.save()
    
    messages.info(request, f"Starting attempt {progress.attempts + 1} of {video.max_attempts}")
    return redirect('quiz', video_id=video.id)