from django.shortcuts import render, redirect
from django.db import transaction, IntegrityError
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password

from ..models import UserAccount, Employee, Store, RoleInStore


def register_view(request):
    director_exists = UserAccount.objects.filter(role__name='директор', is_active=True).exists()
    roles = RoleInStore.objects.exclude(name='директор') if director_exists else RoleInStore.objects.all()
    stores = Store.objects.all()

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        phone = request.POST.get('phone')
        role_id = request.POST.get('role_id')
        store_id = request.POST.get('store_id') or None
        login_str = (request.POST.get('login') or '').strip()
        password_str = request.POST.get('password') or ''

        selected_role = RoleInStore.objects.filter(id=role_id).first()
        if not selected_role or (director_exists and selected_role.name == 'директор'):
            messages.error(request, 'Обрана роль недоступна для реєстрації.')
            return redirect('register')

        if not login_str:
            messages.error(request, 'Логін не може бути порожнім.')
            return redirect('register')

        if len(password_str) < 6:
            messages.error(request, 'Пароль має містити щонайменше 6 символів.')
            return redirect('register')

        if UserAccount.objects.filter(login=login_str).exists():
            messages.error(request, 'Користувач із таким логіном вже існує.')
            return redirect('register')

        try:
            with transaction.atomic():
                emp = Employee.objects.create(
                    full_name=full_name,
                    position=position,
                    phone=phone,
                    store_id=store_id
                )
                UserAccount.objects.create(
                    employee=emp,
                    login=login_str,
                    password_hash=make_password(password_str),
                    role=selected_role,
                    is_active=True
                )
            messages.success(request, 'Реєстрація успішна! Тепер увійдіть у систему.')
            return redirect('login')
        except IntegrityError:
            messages.error(request, 'Помилка при створенні акаунту. Перевірте унікальність даних.')

    return render(request, 'register.html', {'roles': roles, 'stores': stores})


def login_view(request):
    if request.method == 'POST':
        login_input = request.POST.get('login')
        password_input = request.POST.get('password')
        account = UserAccount.objects.select_related('role', 'employee__store').filter(
            login=login_input, is_active=True
        ).first()

        if account and check_password(password_input, account.password_hash):
            request.session['user_account_id'] = account.id
            role_name = account.role.name.lower()
            if role_name == 'директор':
                return redirect('director_dashboard')
            elif role_name == 'продавець-консультант':
                return redirect('cashier_dashboard')
            elif role_name == 'менеджер':
                return redirect('manager_dashboard')
            elif role_name == 'бухгалтер':
                return redirect('accountant_dashboard')
            else:
                messages.info(request, f'Роль "{account.role.name}" ще не налаштована.')
                return redirect('login')

        messages.error(request, 'Невірний логін або пароль, або акаунт деактивовано.')
    return render(request, 'login.html')


def logout_view(request):
    request.session.flush()
    return redirect('login')