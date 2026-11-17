from datetime import date, datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, Count
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password

from .models import (
    UserAccount, Employee, Store, RoleInStore, Product, ProductCategory,
    Customer, Sale, SaleItem, ReturnProduct, WorkShift, PriceChange, Salary
)
from .permissions import role_required

def login_view(request):
    if request.method == 'POST':
        login_input = request.POST.get('login')
        password_input = request.POST.get('password')
        account = UserAccount.objects.select_related('role').filter(login=login_input, is_active=True).first()

        if account and check_password(password_input, account.password_hash):
            request.session['user_account_id'] = account.id
            if account.role.name == 'директор':
                return redirect('director_dashboard')
            elif account.role.name == 'продавець-консультант':
                return redirect('cashier_dashboard')
        messages.error(request, 'Невірний логін або пароль')
    return render(request, 'store_app/login.html')


def logout_view(request):
    request.session.flush()
    return redirect('login')

@role_required(['директор'])
def director_dashboard(request):
    today = date.today()
    sales_today = Sale.objects.filter(date=today).aggregate(
        total_sum=Sum('total'),
        receipts_count=Count('id')
    )
    low_stock_products = Product.objects.filter(stock_quantity__lt=5)
    employees_count = Employee.objects.count()
    stores = Store.objects.all()

    context = {
        'account': request.user_account,
        'sales_today': sales_today,
        'low_stock_products': low_stock_products,
        'employees_count': employees_count,
        'stores': stores,
    }
    return render(request, 'store_app/director/dashboard.html', context)


@role_required(['директор'])
def director_employees(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        phone = request.POST.get('phone')
        login_str = request.POST.get('login')
        password_str = request.POST.get('password')
        role_id = request.POST.get('role_id')

        with transaction.atomic():
            emp = Employee.objects.create(full_name=full_name, position=position, phone=phone)
            if login_str and password_str and role_id:
                UserAccount.objects.create(
                    employee=emp,
                    login=login_str,
                    password_hash=make_password(password_str),
                    role_id=role_id,
                    is_active=True
                )
        messages.success(request, f'Співробітника {full_name} успішно додано.')
        return redirect('director_employees')

    employees = Employee.objects.all()
    accounts = UserAccount.objects.select_related('employee', 'role').all()
    roles = RoleInStore.objects.all()
    return render(request, 'store_app/director/employees.html', {
        'employees': employees,
        'accounts': accounts,
        'roles': roles
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
    return render(request, 'store_app/director/stores.html', {'stores': stores})


@role_required(['директор'])
def director_salaries_view(request):
    salaries = Salary.objects.select_related('employee').order_by('-period_month', 'employee__full_name')
    return render(request, 'store_app/director/salaries.html', {'salaries': salaries})

@role_required(['продавець-консультант'])
def cashier_dashboard(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()
    recent_sales = Sale.objects.filter(employee=employee, date=date.today()).order_by('-time')[:10]

    return render(request, 'store_app/cashier/dashboard.html', {
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
        if action == 'open' and not active_shift:
            cash_start = Decimal(request.POST.get('cash_start', '0'))
            WorkShift.objects.create(
                employee=employee,
                open_time=datetime.now(),
                cash_start=cash_start
            )
            messages.success(request, 'Зміну відкрито!')
        elif action == 'close' and active_shift:
            cash_end = Decimal(request.POST.get('cash_end', '0'))
            active_shift.close_time = datetime.now()
            active_shift.cash_end = cash_end
            active_shift.save()
            messages.success(request, 'Зміну закрито!')
        return redirect('cashier_dashboard')


@role_required(['продавець-консультант'])
def create_sale(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()

    if not active_shift:
        messages.error(request, 'Спочатку відкрийте касову зміну!')
        return redirect('cashier_dashboard')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')  # 'готівка', 'картка', 'змішана'
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

                for p_id, qty_str in zip(product_ids, quantities):
                    qty = int(qty_str)
                    if qty <= 0:
                        continue
                    product = Product.objects.select_for_update().get(id=p_id)
                    if product.stock_quantity < qty:
                        raise ValueError(
                            f'Недостатньо товару "{product.name}" на складі (доступно: {product.stock_quantity})')

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
    return render(request, 'store_app/cashier/create_sale.html', {
        'products': products,
        'customers': customers
    })


@role_required(['продавець-консультант'])
def process_return(request):
    if request.method == 'POST':
        sale_item_id = request.POST.get('sale_item_id')
        qty = int(request.POST.get('quantity'))
        reason = request.POST.get('reason')

        sale_item = get_object_or_404(SaleItem, id=sale_item_id)
        if qty > sale_item.quantity:
            messages.error(request, 'Кількість повернення перевищує кількість у чеку.')
            return redirect('process_return')

        with transaction.atomic():
            ReturnProduct.objects.create(
                sale_item=sale_item,
                employee=request.user_account.employee,
                date=date.today(),
                quantity=qty,
                reason=reason
            )
            product = sale_item.product
            product.stock_quantity += qty
            product.save()

        messages.success(request, f'Повернення товару "{product.name}" ({qty} шт.) оформлено.')
        return redirect('cashier_dashboard')

    recent_items = SaleItem.objects.select_related('receipt', 'product').order_by('-id')[:30]
    return render(request, 'store_app/cashier/return_product.html', {'recent_items': recent_items})


@role_required(['продавець-консультант'])
def manage_customers(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email') or None
        discount = Decimal(request.POST.get('discount_percent', '0'))

        Customer.objects.create(
            full_name=full_name,
            phone=phone,
            email=email,
            discount_percent=discount
        )
        messages.success(request, f'Клієнта {full_name} додано до бази.')
        return redirect('manage_customers')

    customers = Customer.objects.all().order_by('-id')
    return render(request, 'store_app/cashier/customers.html', {'customers': customers})



@role_required(['продавець-консультант', 'менеджер'])
def price_control(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        new_price = Decimal(request.POST.get('new_price'))
        product = get_object_or_404(Product, id=product_id)

        with transaction.atomic():
            PriceChange.objects.create(
                product=product,
                old_price=product.sale_price,
                new_price=new_price,
                change_date=date.today(),
                employee=request.user_account.employee
            )
            product.sale_price = new_price
            product.save()

        messages.success(request, f'Ціну на "{product.name}" змінено з {product.sale_price} на {new_price} грн.')
        return redirect('price_control')

    products = Product.objects.select_related('category').all()
    history = PriceChange.objects.select_related('product', 'employee').order_by('-change_date', '-id')[:20]
    return render(request, 'store_app/shared/prices.html', {
        'products': products,
        'history': history,
        'account': request.user_account
    })