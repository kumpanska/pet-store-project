from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password

from .models import (
    UserAccount, Employee, Store, RoleInStore, Product, ProductCategory,
    Customer, Sale, SaleItem, ReturnProduct, WorkShift, PriceChange, Salary
)
from .permissions import role_required


def calculate_returns_sum(queryset):
    expr = ExpressionWrapper(
        F('sale_item__sale_price') * F('quantity') * (Decimal('100') - F('sale_item__discount')) / Decimal('100'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    total = queryset.aggregate(total_ret=Sum(expr))['total_ret'] or Decimal('0.00')
    return round(total, 2)
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
        login_str = request.POST.get('login')
        password_str = request.POST.get('password')

        selected_role = RoleInStore.objects.filter(id=role_id).first()
        if not selected_role or (director_exists and selected_role.name == 'директор'):
            messages.error(request, 'Обрана роль недоступна для реєстрації.')
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
            if account.role.name == 'директор':
                return redirect('director_dashboard')
            elif account.role.name == 'продавець-консультант':
                return redirect('cashier_dashboard')
            else:
                messages.info(request, f'Роль "{account.role.name}" ще в розробці.')
                return redirect('login')

        messages.error(request, 'Невірний логін або пароль, або акаунт деактивовано.')
    return render(request, 'login.html')


def logout_view(request):
    request.session.flush()
    return redirect('login')

@role_required(['директор'])
def director_dashboard(request):
    today = date.today()

    today_sales_agg = Sale.objects.filter(date=today).aggregate(
        total_sum=Sum('total'), receipts_count=Count('id')
    )
    today_returns = calculate_returns_sum(ReturnProduct.objects.filter(date=today))
    sales_today = {
        'total_sum': (today_sales_agg['total_sum'] or Decimal('0.00')) - today_returns,
        'receipts_count': today_sales_agg['receipts_count'] or 0,
        'returns_sum': today_returns
    }

    month_sales_agg = Sale.objects.filter(
        date__year=today.year, date__month=today.month
    ).aggregate(total_sum=Sum('total'), receipts_count=Count('id'))
    month_returns = calculate_returns_sum(
        ReturnProduct.objects.filter(date__year=today.year, date__month=today.month)
    )
    sales_month = {
        'total_sum': (month_sales_agg['total_sum'] or Decimal('0.00')) - month_returns,
        'receipts_count': month_sales_agg['receipts_count'] or 0,
        'returns_sum': month_returns
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
    recent_sales = Sale.objects.select_related('employee__store', 'customer').order_by('-date', '-time')[:10]
    employees_count = Employee.objects.count()
    stores = Store.objects.all()

    context = {
        'account': request.user_account,
        'sales_today': sales_today,
        'sales_month': sales_month,
        'sales_all_time': sales_all_time,
        'low_stock_products': low_stock_products,
        'recent_sales': recent_sales,
        'employees_count': employees_count,
        'stores': stores,
    }
    return render(request, 'director/dashboard.html', context)


@role_required(['директор'])
def director_employees(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        phone = request.POST.get('phone')
        login_str = request.POST.get('login')
        password_str = request.POST.get('password')
        role_id = request.POST.get('role_id')
        store_id = request.POST.get('store_id') or None

        selected_role = RoleInStore.objects.filter(id=role_id).first()
        if not selected_role or selected_role.name == 'директор':
            messages.error(request, 'Неможливо створити ще одного директора. Оберіть іншу роль.')
            return redirect('director_employees')

        if login_str and UserAccount.objects.filter(login=login_str).exists():
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

    employees = Employee.objects.select_related('store').all()
    accounts = UserAccount.objects.select_related('employee__store', 'role').filter(is_active=True)
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
def director_salaries_view(request):
    salaries = (
        Salary.objects
        .select_related('employee__store')
        .filter(employee__useraccount__is_active=True)
        .order_by('-period_month', 'employee__full_name')
    )
    total_payroll = salaries.aggregate(total_sum=Sum('total'))['total_sum'] or Decimal('0.00')

    return render(request, 'director/salaries.html', {
        'account': request.user_account,
        'salaries': salaries,
        'total_payroll': total_payroll
    })

@role_required(['продавець-консультант'])
def cashier_dashboard(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()
    recent_sales = Sale.objects.filter(employee=employee, date=date.today()).order_by('-time')[:10]

    return render(request, 'cashier/dashboard.html', {
        'account': request.user_account,
        'active_shift': active_shift,
        'recent_sales': recent_sales
    })


@role_required(['продавець-консультант'])
def shift_manage(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'open' and not active_shift:
                cash_start = Decimal(request.POST.get('cash_start', '0'))
                if cash_start < 0:
                    raise ValueError
                WorkShift.objects.create(
                    employee=employee,
                    open_time=datetime.now(),
                    cash_start=cash_start
                )
                messages.success(request, 'Зміну відкрито!')
            elif action == 'close' and active_shift:
                cash_end = Decimal(request.POST.get('cash_end', '0'))
                if cash_end < 0:
                    raise ValueError
                active_shift.close_time = datetime.now()
                active_shift.cash_end = cash_end
                active_shift.save()
                messages.success(request, 'Зміну закрито!')
        except (InvalidOperation, ValueError):
            messages.error(request, 'Введіть коректну суму готівки (невід’ємне число).')

    return redirect('cashier_dashboard')


@role_required(['продавець-консультант'])
def create_sale(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()

    if not active_shift:
        messages.error(request, 'Спочатку відкрийте касову зміну!')
        return redirect('cashier_dashboard')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        customer_id = request.POST.get('customer_id') or None
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')

        customer = Customer.objects.filter(id=customer_id).first() if customer_id else None
        discount_pct = customer.discount_percent if customer else Decimal('0')

        try:
            with transaction.atomic():
                sale = Sale.objects.create(
                    date=date.today(),
                    time=datetime.now().time(),
                    payment_method=payment_method,
                    total=Decimal('0'),
                    customer=customer,
                    employee=employee
                )

                total_receipt = Decimal('0')
                items_created = 0

                for p_id, qty_str in zip(product_ids, quantities):
                    qty = int(qty_str)
                    if qty <= 0:
                        continue
                    product = Product.objects.select_for_update().get(id=p_id)
                    if product.stock_quantity < qty:
                        raise ValueError(
                            f'Недостатньо товару "{product.name}" на складі (доступно: {product.stock_quantity})'
                        )

                    item_price = product.sale_price
                    line_total = (item_price * qty) * (Decimal('100') - discount_pct) / Decimal('100')

                    SaleItem.objects.create(
                        receipt=sale,
                        product=product,
                        quantity=qty,
                        sale_price=item_price,
                        discount=discount_pct
                    )

                    product.stock_quantity -= qty
                    product.save()
                    total_receipt += line_total
                    items_created += 1

                if items_created == 0:
                    raise ValueError('Додайте хоча б один товар із кількістю більше 0.')

                sale.total = round(total_receipt, 2)
                sale.save()

                active_shift.total_sales += sale.total
                active_shift.save()

            messages.success(request, f'Чек №{sale.id} успішно проведено на суму {sale.total} грн.')
            return redirect('cashier_dashboard')

        except ValueError as e:
            messages.error(request, str(e))

    products = Product.objects.filter(stock_quantity__gt=0)
    customers = Customer.objects.all()
    return render(request, 'cashier/create_sale.html', {
        'account': request.user_account,
        'products': products,
        'customers': customers
    })


@role_required(['продавець-консультант'])
def process_return(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()

    if request.method == 'POST':
        sale_item_id = request.POST.get('sale_item_id')
        reason = request.POST.get('reason')
        try:
            qty = int(request.POST.get('quantity', '0'))
            if qty <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'Введіть коректну кількість товару для повернення.')
            return redirect('process_return')

        sale_item = get_object_or_404(SaleItem, id=sale_item_id)

        already_returned = ReturnProduct.objects.filter(sale_item=sale_item).aggregate(
            total_qty=Sum('quantity')
        )['total_qty'] or 0

        available_to_return = sale_item.quantity - already_returned
        if qty > available_to_return:
            messages.error(
                request,
                f'Неможливо повернути {qty} шт. Доступно до повернення за цим чеком: {available_to_return} шт.'
            )
            return redirect('process_return')

        refund_amount = round(
            (sale_item.sale_price * qty) * (Decimal('100') - sale_item.discount) / Decimal('100'),
            2
        )

        with transaction.atomic():
            ReturnProduct.objects.create(
                sale_item=sale_item,
                employee=employee,
                date=date.today(),
                quantity=qty,
                reason=reason
            )
            # 1. Повертаємо товар на склад
            product = sale_item.product
            product.stock_quantity += qty
            product.save()

            # 2. Мінусуємо суму повернення з виручки поточної відкритої зміни касира
            if active_shift:
                active_shift.total_sales = max(Decimal('0.00'), active_shift.total_sales - refund_amount)
                active_shift.save()

        messages.success(
            request,
            f'Повернення товару "{product.name}" ({qty} шт.) на суму {refund_amount} грн оформлено та вирахувано з виручки.'
        )
        return redirect('process_return')

    recent_items = SaleItem.objects.select_related('receipt', 'product').order_by('-id')[:30]
    returns_history = (
        ReturnProduct.objects
        .select_related('sale_item__receipt', 'sale_item__product', 'employee')
        .order_by('-date', '-id')
    )

    return render(request, 'cashier/return_product.html', {
        'account': request.user_account,
        'recent_items': recent_items,
        'returns_history': returns_history
    })


@role_required(['продавець-консультант'])
def manage_customers(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email') or None

        try:
            discount = Decimal(request.POST.get('discount_percent', '0'))
            if discount < 0 or discount > 100:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, 'Знижка має бути числом від 0 до 100%.')
            return redirect('manage_customers')

        try:
            Customer.objects.create(
                full_name=full_name,
                phone=phone,
                email=email,
                discount_percent=discount
            )
            messages.success(request, f'Клієнта {full_name} додано до бази.')
        except IntegrityError:
            messages.error(request, 'Клієнт із таким телефоном або email уже зареєстрований.')

        return redirect('manage_customers')

    customers = Customer.objects.all().order_by('-id')
    return render(request, 'cashier/customers.html', {
        'account': request.user_account,
        'customers': customers
    })

@role_required(['продавець-консультант', 'менеджер'])
def price_control(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        try:
            new_price = Decimal(request.POST.get('new_price'))
            if new_price < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, 'Введіть коректну ціну.')
            return redirect('price_control')

        product = get_object_or_404(Product, id=product_id)
        old_price = product.sale_price

        with transaction.atomic():
            PriceChange.objects.create(
                product=product,
                old_price=old_price,
                new_price=new_price,
                change_date=date.today(),
                employee=request.user_account.employee
            )
            product.sale_price = new_price
            product.save()

        messages.success(request, f'Ціну на "{product.name}" змінено з {old_price} на {new_price} грн.')
        return redirect('price_control')

    products = Product.objects.select_related('category').all()
    history = PriceChange.objects.select_related('product', 'employee').order_by('-change_date', '-id')[:20]
    return render(request, 'shared/prices.html', {
        'products': products,
        'history': history,
        'account': request.user_account
    })