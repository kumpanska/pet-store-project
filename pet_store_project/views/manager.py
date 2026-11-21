from datetime import date
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, IntegrityError
from django.contrib import messages

from ..models import (
    Product, ProductCategory, Supplier, Store, GoodsReceipt,
    InventoryCheck, StockTransfer, WriteOffAct, WriteOffItem,
    SupplierOrder, SupplierOrderItem
)
from ..permissions import role_required


@role_required(['менеджер'])
def manager_dashboard(request):
    low_stock = Product.objects.select_related('category', 'supplier').filter(stock_quantity__lt=5)
    pending_orders = SupplierOrder.objects.select_related('supplier').exclude(status='виконано').order_by('-date')
    recent_transfers = StockTransfer.objects.select_related('from_store', 'to_store', 'product').order_by('-date', '-id')[:5]
    recent_write_offs = WriteOffAct.objects.select_related('employee').order_by('-date', '-id')[:5]

    return render(request, 'manager/dashboard.html', {
        'account': request.user_account,
        'low_stock': low_stock,
        'pending_orders': pending_orders,
        'recent_transfers': recent_transfers,
        'recent_write_offs': recent_write_offs,
        'total_products': Product.objects.count(),
        'total_suppliers': Supplier.objects.count(),
    })


@role_required(['менеджер'])
def manager_catalog(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_category':
            name = (request.POST.get('name') or '').strip()
            description = request.POST.get('description') or ''
            try:
                ProductCategory.objects.create(name=name, description=description)
                messages.success(request, f'Категорію "{name}" додано.')
            except IntegrityError:
                messages.error(request, 'Категорія з такою назвою вже існує.')
            return redirect('manager_catalog')

        if action == 'create_product':
            try:
                Product.objects.create(
                    name=request.POST.get('name'),
                    barcode=request.POST.get('barcode'),
                    sale_price=Decimal(request.POST.get('sale_price')),
                    purchase_price=Decimal(request.POST.get('purchase_price')),
                    stock_quantity=int(request.POST.get('stock_quantity', 0)),
                    category_id=request.POST.get('category_id'),
                    supplier_id=request.POST.get('supplier_id'),
                )
                messages.success(request, 'Нову картку товару створено.')
            except (IntegrityError, InvalidOperation, ValueError):
                messages.error(request, 'Помилка створення товару. Перевірте унікальність штрихкоду та ціни.')
            return redirect('manager_catalog')

        if action == 'edit_product':
            product = get_object_or_404(Product, id=request.POST.get('product_id'))
            try:
                product.name = request.POST.get('name')
                product.barcode = request.POST.get('barcode')
                product.purchase_price = Decimal(request.POST.get('purchase_price'))
                product.sale_price = Decimal(request.POST.get('sale_price'))
                product.category_id = request.POST.get('category_id')
                product.supplier_id = request.POST.get('supplier_id')
                product.save()
                messages.success(request, f'Картку товару "{product.name}" оновлено.')
            except (IntegrityError, InvalidOperation):
                messages.error(request, 'Помилка оновлення картки товару.')
            return redirect('manager_catalog')

    return render(request, 'manager/catalog.html', {
        'account': request.user_account,
        'products': Product.objects.select_related('category', 'supplier').all().order_by('name'),
        'categories': ProductCategory.objects.all(),
        'suppliers': Supplier.objects.all(),
    })


@role_required(['менеджер'])
def manager_inventory(request):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=request.POST.get('product_id'))
        try:
            actual_qty = int(request.POST.get('actual_quantity'))
            if actual_qty < 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'Фактична кількість має бути невід’ємним цілим числом.')
            return redirect('manager_inventory')

        expected_qty = product.stock_quantity
        diff = actual_qty - expected_qty

        with transaction.atomic():
            InventoryCheck.objects.create(
                date=date.today(),
                product=product,
                expected_quantity=expected_qty,
                actual_quantity=actual_qty,
                employee=request.user_account.employee
            )
            product.stock_quantity = actual_qty
            product.save(update_fields=['stock_quantity'])

        messages.success(
            request,
            f'Інвентаризацію "{product.name}" проведено. За обліком: {expected_qty}, фактично: {actual_qty} (різниця: {diff:+d}).'
        )
        return redirect('manager_inventory')

    checks = InventoryCheck.objects.select_related('product', 'employee').order_by('-date', '-id')[:30]
    return render(request, 'manager/inventory.html', {
        'account': request.user_account,
        'products': Product.objects.all().order_by('name'),
        'checks': checks,
    })


@role_required(['менеджер'])
def manager_transfers(request):
    if request.method == 'POST':
        from_store_id = request.POST.get('from_store_id')
        to_store_id = request.POST.get('to_store_id')
        product_id = request.POST.get('product_id')

        if from_store_id == to_store_id:
            messages.error(request, 'Точка відправлення та точка отримання не можуть збігатися.')
            return redirect('manager_transfers')

        try:
            qty = int(request.POST.get('quantity', 0))
            if qty <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'Введіть коректну кількість для переміщення.')
            return redirect('manager_transfers')

        product = get_object_or_404(Product, id=product_id)
        if product.stock_quantity < qty:
            messages.error(request, f'Недостатньо товару "{product.name}" (доступно: {product.stock_quantity} шт.).')
            return redirect('manager_transfers')

        StockTransfer.objects.create(
            date=date.today(),
            from_store_id=from_store_id,
            to_store_id=to_store_id,
            product=product,
            quantity=qty,
            employee=request.user_account.employee
        )
        messages.success(request, f'Переміщення товару "{product.name}" ({qty} шт.) оформлено.')
        return redirect('manager_transfers')

    transfers = StockTransfer.objects.select_related('from_store', 'to_store', 'product', 'employee').order_by('-date', '-id')[:30]
    return render(request, 'manager/transfers.html', {
        'account': request.user_account,
        'stores': Store.objects.all(),
        'products': Product.objects.filter(stock_quantity__gt=0),
        'transfers': transfers,
    })


@role_required(['менеджер'])
def manager_write_offs(request):
    if request.method == 'POST':
        reason = (request.POST.get('reason') or '').strip()
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')

        if not reason:
            messages.error(request, 'Вкажіть причину списання (наприклад, закінчення терміну придатності).')
            return redirect('manager_write_offs')

        try:
            with transaction.atomic():
                act = WriteOffAct.objects.create(
                    date=date.today(),
                    reason=reason,
                    employee=request.user_account.employee
                )
                items_count = 0
                for p_id, qty_str in zip(product_ids, quantities):
                    if not p_id:
                        continue
                    qty = int(qty_str or 0)
                    if qty <= 0:
                        continue
                    product = Product.objects.select_for_update().get(id=p_id)
                    if product.stock_quantity < qty:
                        raise ValueError(f'На складі лише {product.stock_quantity} шт. товару "{product.name}".')

                    WriteOffItem.objects.create(
                        write_off_act=act,
                        product=product,
                        quantity=qty
                    )
                    product.stock_quantity -= qty
                    product.save(update_fields=['stock_quantity'])
                    items_count += 1

                if items_count == 0:
                    raise ValueError('Додайте хоча б один товар до акту списання.')

            messages.success(request, f'Акт списання №{act.id} успішно проведено.')
            return redirect('manager_write_offs')

        except ValueError as e:
            messages.error(request, str(e))

    acts = WriteOffAct.objects.select_related('employee').prefetch_related('items__product').order_by('-date', '-id')[:20]
    return render(request, 'manager/write_offs.html', {
        'account': request.user_account,
        'products': Product.objects.filter(stock_quantity__gt=0),
        'acts': acts,
    })


@role_required(['менеджер'])
def manager_suppliers(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_supplier':
            try:
                Supplier.objects.create(
                    company_name=request.POST.get('company_name'),
                    contact_person=request.POST.get('contact_person'),
                    phone=request.POST.get('phone'),
                    email=request.POST.get('email'),
                )
                messages.success(request, 'Постачальника додано до довідника.')
            except IntegrityError:
                messages.error(request, 'Постачальник із таким email вже існує.')
            return redirect('manager_suppliers')

        if action == 'create_order':
            supplier_id = request.POST.get('supplier_id')
            product_ids = request.POST.getlist('product_id[]')
            quantities = request.POST.getlist('quantity[]')

            try:
                with transaction.atomic():
                    order = SupplierOrder.objects.create(
                        supplier_id=supplier_id,
                        date=date.today(),
                        status='створено',
                        total=Decimal('0.00')
                    )
                    order_total = Decimal('0.00')
                    count = 0
                    for p_id, qty_str in zip(product_ids, quantities):
                        if not p_id:
                            continue
                        qty = int(qty_str or 0)
                        if qty <= 0:
                            continue
                        product = Product.objects.get(id=p_id)
                        SupplierOrderItem.objects.create(
                            supplier_order=order,
                            product=product,
                            quantity=qty,
                            price=product.purchase_price
                        )
                        order_total += product.purchase_price * qty
                        count += 1

                    if count == 0:
                        raise ValueError('Оберіть хоча б один товар для замовлення.')

                    order.total = round(order_total, 2)
                    order.save(update_fields=['total'])

                messages.success(request, f'Замовлення постачальнику №{order.id} на суму {order.total} грн сформовано.')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('manager_suppliers')

        if action == 'update_order_status':
            order = get_object_or_404(SupplierOrder, id=request.POST.get('order_id'))
            order.status = request.POST.get('status')
            order.save(update_fields=['status'])
            messages.success(request, f'Статус замовлення №{order.id} змінено на "{order.status}".')
            return redirect('manager_suppliers')

    return render(request, 'manager/suppliers.html', {
        'account': request.user_account,
        'suppliers': Supplier.objects.all(),
        'products': Product.objects.select_related('supplier').all(),
        'low_stock_products': Product.objects.select_related('supplier').filter(stock_quantity__lt=5),
        'orders': SupplierOrder.objects.select_related('supplier').prefetch_related('items__product').order_by('-date', '-id')[:25],
        'receipts_history': GoodsReceipt.objects.select_related('supplier').order_by('-date', '-id')[:20],
    })