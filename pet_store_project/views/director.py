from datetime import date
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.contrib import messages
from django.contrib.auth.hashers import make_password

from ..models import (
    UserAccount, Employee, Store, RoleInStore, Product,
    Sale, SaleItem, ReturnProduct, Salary
)
from ..permissions import role_required
from .helpers import calculate_returns_sum


@role_required(['директор'])
def director_dashboard(request):
    today = date.today()
    date_from_str = request.GET.get('date_from') or today.replace(day=1).isoformat()
    date_to_str = request.GET.get('date_to') or today.isoformat()

    # Виручка за сьогодні
    today_sales_agg = Sale.objects.filter(date=today).aggregate(
        total_sum=Sum('total'), receipts_count=Count('id')
    )
    today_returns = calculate_returns_sum(ReturnProduct.objects.filter(date=today))
    sales_today = {
        'total_sum': (today_sales_agg['total_sum'] or Decimal('0.00')) - today_returns,
        'receipts_count': today_sales_agg['receipts_count'] or 0,
        'returns_sum': today_returns
    }

    period_sales_qs = Sale.objects.filter(date__range=[date_from_str, date_to_str])
    period_sales_agg = period_sales_qs.aggregate(
        total_sum=Sum('total'), receipts_count=Count('id')
    )
    period_returns = calculate_returns_sum(
        ReturnProduct.objects.filter(date__range=[date_from_str, date_to_str])
    )
    sales_period = {
        'total_sum': (period_sales_agg['total_sum'] or Decimal('0.00')) - period_returns,
        'receipts_count': period_sales_agg['receipts_count'] or 0,
        'returns_sum': period_returns
    }

    all_sales_agg = Sale.objects.aggregate(
        total_sum=Sum('total'), receipts_count=Count('id')
    )
    all_returns = calculate_returns_sum(ReturnProduct.objects.all())
    sales_all_time = {
        'total_sum': (all_sales_agg['total_sum'] or Decimal('0.00')) - all_returns,
        'receipts_count': all_sales_agg['receipts_count'] or 0,
        'returns_sum': all_returns
    }

    low_stock_products = Product.objects.filter(stock_quantity__lt=5)
    recent_sales = period_sales_qs.select_related('employee__store', 'customer').order_by('-date', '-time')[:20]
    employees_count = Employee.objects.count()
    stores = Store.objects.all()

    return render(request, 'director/dashboard.html', {
        'account': request.user_account,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'sales_today': sales_today,
        'sales_period': sales_period,
        'sales_all_time': sales_all_time,
        'low_stock_products': low_stock_products,
        'recent_sales': recent_sales,
        'employees_count': employees_count,
        'stores': stores,
    })


@role_required(['директор'])
def director_employees(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'toggle_access':
            acc_id = request.POST.get('account_id')
            acc = get_object_or_404(UserAccount, id=acc_id)
            if acc.role.name == 'директор':
                messages.error(request, 'Неможливо деактивувати обліковий запис директора.')
            else:
                acc.is_active = not acc.is_active
                acc.save(update_fields=['is_active'])
                status_text = 'активовано' if acc.is_active else 'заблоковано'
                messages.success(request, f'Акаунт {acc.login} успішно {status_text}.')
            return redirect('director_employees')

        if action == 'update_role_store':
            emp_id = request.POST.get('employee_id')
            role_id = request.POST.get('role_id')
            store_id = request.POST.get('store_id') or None
            emp = get_object_or_404(Employee, id=emp_id)
            emp.store_id = store_id
            emp.save(update_fields=['store_id'])

            if role_id and hasattr(emp, 'useraccount'):
                new_role = RoleInStore.objects.filter(id=role_id).exclude(name='директор').first()
                if new_role and emp.useraccount.role.name != 'директор':
                    emp.useraccount.role = new_role
                    emp.useraccount.save(update_fields=['role'])

            messages.success(request, f'Дані співробітника {emp.full_name} оновлено.')
            return redirect('director_employees')

        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        phone = request.POST.get('phone')
        login_str = (request.POST.get('login') or '').strip()
        password_str = request.POST.get('password') or ''
        role_id = request.POST.get('role_id')
        store_id = request.POST.get('store_id') or None

        selected_role = RoleInStore.objects.filter(id=role_id).first()
        if not selected_role or selected_role.name == 'директор':
            messages.error(request, 'Неможливо створити ще одного директора. Оберіть іншу роль.')
            return redirect('director_employees')

        if login_str or password_str:
            if not login_str:
                messages.error(request, 'Вкажіть логін для створення облікового запису.')
                return redirect('director_employees')

            if len(password_str) < 6:
                messages.error(request, 'Пароль має містити щонайменше 6 символів.')
                return redirect('director_employees')

            if UserAccount.objects.filter(login=login_str).exists():
                messages.error(request, f'Логін "{login_str}" уже зайнятий.')
                return redirect('director_employees')

        try:
            with transaction.atomic():
                emp = Employee.objects.create(
                    full_name=full_name,
                    position=position,
                    phone=phone,
                    store_id=store_id
                )
                if login_str and password_str:
                    UserAccount.objects.create(
                        employee=emp,
                        login=login_str,
                        password_hash=make_password(password_str),
                        role=selected_role,
                        is_active=True
                    )
            messages.success(request, f'Співробітника {full_name} успішно додано.')
        except IntegrityError:
            messages.error(request, 'Помилка збереження: перевірте унікальність логіну або даних співробітника.')

        return redirect('director_employees')

    employees = Employee.objects.select_related('store', 'useraccount__role').all()
    accounts = UserAccount.objects.select_related('employee__store', 'role').all()
    roles = RoleInStore.objects.exclude(name='директор')
    stores = Store.objects.all()

    return render(request, 'director/employees.html', {
        'account': request.user_account,
        'employees': employees,
        'accounts': accounts,
        'roles': roles,
        'stores': stores
    })


@role_required(['директор'])
def director_stores(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address')
        store_type = request.POST.get('type')

        Store.objects.create(name=name, address=address, type=store_type)
        messages.success(request, f'Точку "{name}" ({store_type}) додано.')
        return redirect('director_stores')

    stores = Store.objects.all()
    return render(request, 'director/stores.html', {
        'account': request.user_account,
        'stores': stores
    })


@role_required(['директор'])
def director_analytics(request):
    today = date.today()
    date_from_str = request.GET.get('date_from') or today.replace(day=1).isoformat()
    date_to_str = request.GET.get('date_to') or today.isoformat()
    store_id = request.GET.get('store_id') or ''

    sales_qs = Sale.objects.filter(date__range=[date_from_str, date_to_str])
    items_qs = SaleItem.objects.filter(receipt__date__range=[date_from_str, date_to_str])

    if store_id:
        sales_qs = sales_qs.filter(employee__store_id=store_id)
        items_qs = items_qs.filter(receipt__employee__store_id=store_id)

    revenue_expr = ExpressionWrapper(
        F('sale_price') * F('quantity') * (Decimal('100') - F('discount')) / Decimal('100'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    profit_expr = ExpressionWrapper(
        (F('sale_price') * (Decimal('100') - F('discount')) / Decimal('100') - F('product__purchase_price')) * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    category_stats = (
        items_qs.values('product__category__name')
        .annotate(
            qty_sold=Sum('quantity'),
            revenue=Sum(revenue_expr),
            gross_profit=Sum(profit_expr)
        )
        .order_by('-revenue')
    )

    top_products = (
        items_qs.values('product__name', 'product__barcode', 'product__stock_quantity')
        .annotate(
            qty_sold=Sum('quantity'),
            revenue=Sum(revenue_expr),
            gross_profit=Sum(profit_expr)
        )
        .order_by('-revenue')[:15]
    )

    sold_product_ids = items_qs.values_list('product_id', flat=True).distinct()
    illiquid_products = Product.objects.filter(stock_quantity__gt=0).exclude(id__in=sold_product_ids)

    store_stats = (
        sales_qs.values('employee__store__name')
        .annotate(receipts=Count('id'), total_revenue=Sum('total'))
        .order_by('-total_revenue')
    )

    employee_stats = (
        sales_qs.values('employee__full_name', 'employee__store__name')
        .annotate(receipts=Count('id'), total_revenue=Sum('total'))
        .order_by('-total_revenue')
    )

    return render(request, 'director/analytics.html', {
        'account': request.user_account,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'selected_store_id': store_id,
        'stores': Store.objects.all(),
        'category_stats': category_stats,
        'top_products': top_products,
        'illiquid_products': illiquid_products,
        'store_stats': store_stats,
        'employee_stats': employee_stats,
    })