from datetime import date
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password

from ..models import (
    Product, ProductCategory, Store, ProductStock,
    Customer, OnlineOrder, OnlineOrderItem
)
from .helpers import get_active_promo_for_product, get_customer_discount


def _get_cart(request):
    return request.session.get('shop_cart', {})


def _save_cart(request, cart):
    request.session['shop_cart'] = cart
    request.session.modified = True


def _get_shop_customer(request):
    customer_id = request.session.get('shop_customer_id')
    if not customer_id:
        return None
    return Customer.objects.filter(id=customer_id).first()


def _sync_product_total_stock(product):
    total_qty = ProductStock.objects.filter(product=product).aggregate(s=Sum('quantity'))['s'] or 0
    product.stock_quantity = total_qty
    product.save(update_fields=['stock_quantity'])


def shop_register(request):
    if _get_shop_customer(request):
        return redirect('shop_catalog')

    if request.method == 'POST':
        full_name = (request.POST.get('full_name') or '').strip()
        phone = (request.POST.get('phone') or '').strip()
        email = (request.POST.get('email') or '').strip() or None
        password = request.POST.get('password') or ''
        password_confirm = request.POST.get('password_confirm') or ''

        if not full_name or not phone or len(password) < 4:
            messages.error(request, 'Заповніть ПІБ, телефон та пароль (мінімум 4 символи).')
            return redirect('shop_register')

        if password != password_confirm:
            messages.error(request, 'Паролі не збігаються.')
            return redirect('shop_register')

        existing_customer = Customer.objects.filter(phone=phone).first()
        if existing_customer:
            if existing_customer.password_hash:
                messages.error(request, 'Клієнт із таким номером телефону вже зареєстрований. Увійдіть в акаунт.')
                return redirect('shop_login')
            existing_customer.full_name = full_name
            if email:
                existing_customer.email = email
            existing_customer.password_hash = make_password(password)
            existing_customer.save(update_fields=['full_name', 'email', 'password_hash'])
            customer = existing_customer
            messages.success(
                request,
                f'Вашу картку лояльності активовано! Поточна знижка: {customer.discount_percent:.0f}%.'
            )
        else:
            customer = Customer.objects.create(
                full_name=full_name,
                phone=phone,
                email=email,
                discount_percent=Decimal('3.00'),
                password_hash=make_password(password),
            )
            messages.success(request, 'Реєстрація успішна! Вам нараховано стартову знижку 3%.')

        request.session['shop_customer_id'] = customer.id
        return redirect('shop_catalog')

    return render(request, 'shop/register.html', {
        'shop_customer': None,
        'cart_count': sum(_get_cart(request).values()),
    })


def shop_login(request):
    if _get_shop_customer(request):
        return redirect('shop_catalog')

    if request.method == 'POST':
        phone = (request.POST.get('phone') or '').strip()
        password = request.POST.get('password') or ''

        customer = Customer.objects.filter(phone=phone).first()
        if not customer or not customer.password_hash or not check_password(password, customer.password_hash):
            messages.error(request, 'Невірний номер телефону або пароль.')
            return redirect('shop_login')

        request.session['shop_customer_id'] = customer.id
        messages.success(request, f'Вітаємо, {customer.full_name}!')
        return redirect('shop_catalog')

    return render(request, 'shop/login.html', {
        'shop_customer': None,
        'cart_count': sum(_get_cart(request).values()),
    })


def shop_logout(request):
    request.session.pop('shop_customer_id', None)
    messages.info(request, 'Ви вийшли з особистого кабінету покупця.')
    return redirect('shop_catalog')


def shop_catalog(request):
    category_id = request.GET.get('category') or ''
    store_id = request.GET.get('store') or ''
    query = (request.GET.get('q') or '').strip()

    products_qs = Product.objects.select_related('category', 'supplier').prefetch_related('store_stocks__store').order_by('name')

    if category_id:
        products_qs = products_qs.filter(category_id=category_id)
    if query:
        products_qs = products_qs.filter(name__icontains=query)
    if store_id:
        products_qs = products_qs.filter(store_stocks__store_id=store_id, store_stocks__quantity__gt=0).distinct()

    products = list(products_qs)
    for p in products:
        p.active_promo = get_active_promo_for_product(p)
        if p.active_promo > 0:
            p.promo_price = round(p.sale_price * (Decimal('100') - p.active_promo) / Decimal('100'), 2)
        else:
            p.promo_price = p.sale_price

    cart = _get_cart(request)
    cart_count = sum(cart.values())

    return render(request, 'shop/catalog.html', {
        'shop_customer': _get_shop_customer(request),
        'products': products,
        'categories': ProductCategory.objects.all(),
        'stores': Store.objects.filter(type='магазин'),
        'selected_category': category_id,
        'selected_store': store_id,
        'query': query,
        'cart_count': cart_count,
    })


def shop_cart_action(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        product_id = str(request.POST.get('product_id', ''))
        cart = _get_cart(request)

        if action == 'add' and product_id:
            product = get_object_or_404(Product, id=product_id)
            qty = max(1, int(request.POST.get('quantity', 1)))
            new_qty = cart.get(product_id, 0) + qty
            if new_qty > product.stock_quantity:
                messages.error(request, f'На жаль, доступно лише {product.stock_quantity} шт. товару "{product.name}".')
            else:
                cart[product_id] = new_qty
                _save_cart(request, cart)
                messages.success(request, f'Товар "{product.name}" додано до кошика.')
            return redirect(request.POST.get('next') or 'shop_catalog')

        if action == 'update' and product_id in cart:
            qty = int(request.POST.get('quantity', 0))
            if qty <= 0:
                cart.pop(product_id, None)
            else:
                product = get_object_or_404(Product, id=product_id)
                cart[product_id] = min(qty, product.stock_quantity)
            _save_cart(request, cart)

        if action == 'remove' and product_id in cart:
            cart.pop(product_id, None)
            _save_cart(request, cart)

        if action == 'clear':
            _save_cart(request, {})

    return redirect('shop_checkout')


def shop_checkout(request):
    cart = _get_cart(request)
    shop_customer = _get_shop_customer(request)

    if shop_customer:
        customer = shop_customer
        phone_lookup = shop_customer.phone
    else:
        phone_lookup = (request.GET.get('phone') or request.POST.get('customer_phone') or '').strip()
        customer = Customer.objects.filter(phone=phone_lookup).first() if phone_lookup else None

    customer_discount = get_customer_discount(customer) if customer else Decimal('0.00')

    cart_items = []
    subtotal = Decimal('0.00')
    total_with_discount = Decimal('0.00')

    for p_id_str, qty in list(cart.items()):
        product = Product.objects.prefetch_related('store_stocks__store').filter(id=p_id_str).first()
        if not product or product.stock_quantity <= 0:
            cart.pop(p_id_str, None)
            _save_cart(request, cart)
            continue

        qty = min(qty, product.stock_quantity)
        promo_disc = get_active_promo_for_product(product)
        applied_disc = max(customer_discount, promo_disc)

        raw_line = product.sale_price * qty
        final_line = round(raw_line * (Decimal('100') - applied_disc) / Decimal('100'), 2)

        stock_by_store = {ps.store_id: ps.quantity for ps in product.store_stocks.all()}

        cart_items.append({
            'product': product,
            'quantity': qty,
            'applied_discount': applied_disc,
            'raw_line': raw_line,
            'final_line': final_line,
            'stock_by_store': stock_by_store,
        })
        subtotal += raw_line
        total_with_discount += final_line

    if request.method == 'POST' and request.POST.get('action') == 'place_order':
        if not cart_items:
            messages.error(request, 'Ваш кошик порожній.')
            return redirect('shop_catalog')

        customer_name = (request.POST.get('customer_name') or '').strip()
        customer_phone = shop_customer.phone if shop_customer else (request.POST.get('customer_phone') or '').strip()
        delivery_type = request.POST.get('delivery_type', 'самовивіз')
        pickup_store_id = request.POST.get('pickup_store_id') or None
        delivery_address = (request.POST.get('delivery_address') or '').strip()
        payment_method = request.POST.get('payment_method', 'при отриманні')
        comment = (request.POST.get('comment') or '').strip()

        if not customer_name or not customer_phone:
            messages.error(request, 'Вкажіть ваше ім’я та контактний телефон.')
            return redirect('shop_checkout')

        if delivery_type == 'самовивіз' and not pickup_store_id:
            messages.error(request, 'Оберіть магазин для самовивозу.')
            return redirect('shop_checkout')

        if delivery_type == 'доставка' and not delivery_address:
            messages.error(request, 'Вкажіть місто та адресу / відділення пошти для доставки.')
            return redirect('shop_checkout')

        try:
            with transaction.atomic():
                if shop_customer:
                    customer_obj = shop_customer
                else:
                    customer_obj, created = Customer.objects.get_or_create(
                        phone=customer_phone,
                        defaults={
                            'full_name': customer_name,
                            'discount_percent': Decimal('3.00'),
                        }
                    )
                cust_disc = get_customer_discount(customer_obj)

                order = OnlineOrder.objects.create(
                    customer=customer_obj,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    delivery_type=delivery_type,
                    pickup_store_id=pickup_store_id if delivery_type == 'самовивіз' else None,
                    delivery_address=delivery_address if delivery_type == 'доставка' else None,
                    payment_method=payment_method,
                    is_paid=(payment_method == 'онлайн карткою'),
                    status='нове',
                    total=Decimal('0.00'),
                    comment=comment or None,
                )

                order_total = Decimal('0.00')
                transfer_needed_notes = []

                for item in cart_items:
                    product = Product.objects.select_for_update().get(id=item['product'].id)
                    qty = item['quantity']

                    if product.stock_quantity < qty:
                        raise ValueError(
                            f'Поки ви оформлювали замовлення, залишок "{product.name}" зменшився до {product.stock_quantity} шт.'
                        )

                    remaining_to_reserve = qty
                    if delivery_type == 'самовивіз' and pickup_store_id:
                        store_stock = ProductStock.objects.select_for_update().filter(
                            product=product, store_id=pickup_store_id
                        ).first()
                        if store_stock and store_stock.quantity > 0:
                            take = min(store_stock.quantity, remaining_to_reserve)
                            store_stock.quantity -= take
                            store_stock.save(update_fields=['quantity'])
                            remaining_to_reserve -= take

                        if remaining_to_reserve > 0:
                            transfer_needed_notes.append(f'{product.name} ({remaining_to_reserve} шт.)')

                    # Добираємо залишок зі складу або інших точок
                    if remaining_to_reserve > 0:
                        other_stocks = ProductStock.objects.select_for_update().filter(
                            product=product, quantity__gt=0
                        ).order_by('-store__type', '-quantity')
                        for st in other_stocks:
                            if remaining_to_reserve <= 0:
                                break
                            take = min(st.quantity, remaining_to_reserve)
                            st.quantity -= take
                            st.save(update_fields=['quantity'])
                            remaining_to_reserve -= take

                    _sync_product_total_stock(product)

                    applied_disc = max(cust_disc, get_active_promo_for_product(product))
                    line_sum = round((product.sale_price * qty) * (Decimal('100') - applied_disc) / Decimal('100'), 2)

                    OnlineOrderItem.objects.create(
                        online_order=order,
                        product=product,
                        quantity=qty,
                        unit_price=product.sale_price,
                        discount=applied_disc,
                    )
                    order_total += line_sum

                if transfer_needed_notes:
                    extra_note = 'Потрібне підвезення зі складу: ' + ', '.join(transfer_needed_notes)
                    order.comment = f'{order.comment} | {extra_note}' if order.comment else extra_note

                order.total = round(order_total, 2)
                order.save(update_fields=['total', 'comment'])

            _save_cart(request, {})
            messages.success(
                request,
                f'Ваше замовлення №{order.id} на суму {order.total} грн успішно оформлено!'
            )
            return redirect('shop_my_orders') if shop_customer else redirect(f'/shop/orders/?phone={customer_phone}')

        except ValueError as e:
            messages.error(request, str(e))
            return redirect('shop_checkout')

    pickup_stores = Store.objects.filter(type='магазин')
    return render(request, 'shop/checkout.html', {
        'shop_customer': shop_customer,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'total_with_discount': total_with_discount,
        'discount_saved': subtotal - total_with_discount,
        'customer': customer,
        'customer_discount': customer_discount,
        'phone_lookup': phone_lookup,
        'pickup_stores': pickup_stores,
        'cart_count': sum(cart.values()),
    })


def shop_my_orders(request):
    shop_customer = _get_shop_customer(request)
    phone = shop_customer.phone if shop_customer else (request.GET.get('phone') or '').strip()
    orders = []
    customer = shop_customer

    if phone:
        if not customer:
            customer = Customer.objects.filter(phone=phone).first()
        orders = (
            OnlineOrder.objects
            .select_related('pickup_store')
            .prefetch_related('items__product')
            .filter(customer_phone=phone)
            .order_by('-created_at')
        )

    cart = _get_cart(request)
    return render(request, 'shop/my_orders.html', {
        'shop_customer': shop_customer,
        'phone': phone,
        'customer': customer,
        'orders': orders,
        'cart_count': sum(cart.values()),
    })