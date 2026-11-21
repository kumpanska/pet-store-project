from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Sum
from django.contrib import messages

from ..models import (
    Product, Customer, Sale, SaleItem, ReturnProduct,
    WorkShift, Supplier, GoodsReceipt, GoodsReceiptItem
)
from ..permissions import role_required
from .helpers import (
    ALLOWED_DISCOUNTS,
    get_active_promo_for_product,
    get_customer_discount,
    sync_all_customers_and_sales,
    build_shift_report,
)


@role_required(['продавець-консультант'])
def cashier_dashboard(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()
    recent_sales = Sale.objects.filter(employee=employee, date=date.today()).order_by('-time')[:10]
    last_closed_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=False).order_by('-close_time').first()

    x_report = build_shift_report(active_shift) if active_shift else None

    return render(request, 'cashier/dashboard.html', {
        'account': request.user_account,
        'active_shift': active_shift,
        'recent_sales': recent_sales,
        'x_report': x_report,
        'last_closed_shift': last_closed_shift,
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
                z_report = build_shift_report(active_shift)
                messages.success(
                    request,
                    f'Зміну закрито (Z-звіт сформовано)! Готівка: {z_report["cash_sales"]} грн, '
                    f'Картка: {z_report["card_sales"]} грн, Повернення: {z_report["returns_sum"]} грн, '
                    f'Чиста виручка: {z_report["net_revenue"]} грн.'
                )
                return render(request, 'cashier/z_report.html', {
                    'account': request.user_account,
                    'report': z_report,
                    'report_type': 'Z-звіт (Закриття зміни)'
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Введіть коректну суму готівки (невід’ємне число).')

    return redirect('cashier_dashboard')


@role_required(['продавець-консультант'])
def shift_x_report(request):
    employee = request.user_account.employee
    active_shift = WorkShift.objects.filter(employee=employee, close_time__isnull=True).first()
    if not active_shift:
        messages.error(request, 'Немає відкритої зміни для формування X-звіту.')
        return redirect('cashier_dashboard')

    report = build_shift_report(active_shift)
    return render(request, 'cashier/z_report.html', {
        'account': request.user_account,
        'report': report,
        'report_type': 'X-звіт (Проміжний звіт за відкриту зміну)'
    })


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
        customer_discount_pct = get_customer_discount(customer)

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
                    product = Product.objects.select_for_update().select_related('category').get(id=p_id)
                    if product.stock_quantity < qty:
                        raise ValueError(
                            f'Недостатньо товару "{product.name}" на складі (доступно: {product.stock_quantity})'
                        )

                    promo_discount_pct = get_active_promo_for_product(product)
                    applied_discount = max(customer_discount_pct, promo_discount_pct)

                    item_price = product.sale_price
                    line_total = (item_price * qty) * (Decimal('100') - applied_discount) / Decimal('100')

                    SaleItem.objects.create(
                        receipt=sale,
                        product=product,
                        quantity=qty,
                        sale_price=item_price,
                        discount=applied_discount
                    )

                    product.stock_quantity -= qty
                    product.save(update_fields=['stock_quantity'])
                    total_receipt += line_total
                    items_created += 1

                if items_created == 0:
                    raise ValueError('Додайте хоча б один товар із кількістю більше 0.')

                sale.total = round(total_receipt, 2)
                sale.save(update_fields=['total'])

                active_shift.total_sales += sale.total
                active_shift.save(update_fields=['total_sales'])

                if customer:
                    new_discount = get_customer_discount(customer)
                    if customer.discount_percent != new_discount:
                        customer.discount_percent = new_discount
                        customer.save(update_fields=['discount_percent'])

            messages.success(request, f'Чек №{sale.id} успішно проведено на суму {sale.total} грн.')
            return redirect('cashier_dashboard')

        except ValueError as e:
            messages.error(request, str(e))

    products = list(Product.objects.select_related('category').filter(stock_quantity__gt=0))
    for p in products:
        p.active_promo = get_active_promo_for_product(p)

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
            product = sale_item.product
            product.stock_quantity += qty
            product.save(update_fields=['stock_quantity'])

            if active_shift:
                active_shift.total_sales = max(Decimal('0.00'), active_shift.total_sales - refund_amount)
                active_shift.save(update_fields=['total_sales'])

            customer = sale_item.receipt.customer
            if customer:
                new_discount = get_customer_discount(customer, strict_by_spent=True)
                if customer.discount_percent != new_discount:
                    customer.discount_percent = new_discount
                    customer.save(update_fields=['discount_percent'])

        messages.success(
            request,
            f'Повернення товару "{product.name}" ({qty} шт.) на суму {refund_amount} грн оформлено та вирахувано з виручки.'
        )
        return redirect('process_return')

    recent_items = SaleItem.objects.select_related('receipt', 'product').order_by('-id')[:30]
    returns_history = (
        ReturnProduct.objects
        .select_related('sale_item__receipt', 'sale_item__product', 'employee')
        .order_by('-date', '-id')[:20]
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
            discount = Decimal(request.POST.get('discount_percent', '3.00'))
            if discount not in ALLOWED_DISCOUNTS:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, 'Оберіть коректну знижку зі списку: 3%, 5% або 10%.')
            return redirect('manage_customers')

        try:
            Customer.objects.create(
                full_name=full_name,
                phone=phone,
                email=email,
                discount_percent=discount
            )
            messages.success(request, f'Клієнта {full_name} додано до бази зі знижкою {discount:.0f}%.')
        except IntegrityError:
            messages.error(request, 'Клієнт із таким телефоном або email уже зареєстрований.')

        return redirect('manage_customers')

    customers = sync_all_customers_and_sales()
    return render(request, 'cashier/customers.html', {
        'account': request.user_account,
        'customers': customers
    })


@role_required(['продавець-консультант', 'менеджер'])
def goods_receipt_create(request):
    if request.method == 'POST':
        if request.user_account.role.name.lower() != 'продавець-консультант':
            messages.error(request, 'Оформлення прибуткових накладних доступне лише продавцю-консультанту.')
            return redirect('goods_receipt_create')

        supplier_id = request.POST.get('supplier_id')
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')
        purchase_prices = request.POST.getlist('purchase_price[]')

        supplier = get_object_or_404(Supplier, id=supplier_id)

        try:
            with transaction.atomic():
                receipt = GoodsReceipt.objects.create(
                    date=date.today(),
                    total=Decimal('0.00'),
                    supplier=supplier
                )
                total_invoice = Decimal('0.00')
                items_count = 0

                for p_id, qty_str, price_str in zip(product_ids, quantities, purchase_prices):
                    if not p_id:
                        continue
                    qty = int(qty_str or 0)
                    if qty <= 0:
                        continue
                    product = Product.objects.select_for_update().get(id=p_id)
                    p_price = Decimal(price_str) if price_str else product.purchase_price
                    if p_price < 0:
                        raise ValueError('Закупівельна ціна не може бути від’ємною.')

                    GoodsReceiptItem.objects.create(
                        goods_receipt=receipt,
                        product=product,
                        quantity=qty,
                        purchase_price=p_price
                    )

                    product.stock_quantity += qty
                    product.purchase_price = p_price
                    product.save(update_fields=['stock_quantity', 'purchase_price'])

                    total_invoice += p_price * qty
                    items_count += 1

                if items_count == 0:
                    raise ValueError('Додайте хоча б один товар у прибуткову накладну.')

                receipt.total = round(total_invoice, 2)
                receipt.save(update_fields=['total'])

            messages.success(
                request,
                f'Прибуткова накладна №{receipt.id} від "{supplier.company_name}" на суму {receipt.total} грн проведена.'
            )
            return redirect('goods_receipt_create')

        except (InvalidOperation, ValueError) as e:
            messages.error(request, str(e))

    receipts = GoodsReceipt.objects.select_related('supplier').prefetch_related('items__product').order_by('-date', '-id')[:20]
    return render(request, 'cashier/goods_receipts.html', {
        'account': request.user_account,
        'suppliers': Supplier.objects.all(),
        'products': Product.objects.select_related('category', 'supplier').all(),
        'receipts': receipts,
    })