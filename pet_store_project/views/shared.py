from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages

from ..models import Product, ProductCategory, PriceChange
from ..permissions import role_required
from .helpers import ACTIVE_PROMO_DISCOUNTS


@role_required(['продавець-консультант', 'менеджер'])
def price_control(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'change_price')

        if action == 'add_promo':
            title = (request.POST.get('promo_title') or 'Тижнева акція').strip()
            target_type = request.POST.get('target_type')
            target_id = int(request.POST.get('target_id', 0))
            days = int(request.POST.get('duration_days', 7))
            try:
                percent = Decimal(request.POST.get('promo_percent', '0'))
                if percent <= 0 or percent > 90:
                    raise ValueError
            except (InvalidOperation, ValueError):
                messages.error(request, 'Введіть коректний відсоток акційної знижки (від 1 до 90%).')
                return redirect('price_control')

            if target_type == 'category':
                target_obj = get_object_or_404(ProductCategory, id=target_id)
                target_name = f'Категорія: {target_obj.name}'
            else:
                target_obj = get_object_or_404(Product, id=target_id)
                target_name = f'Товар: {target_obj.name}'

            start_dt = date.today()
            end_dt = start_dt + timedelta(days=days)
            key = f'{target_type}_{target_id}'

            ACTIVE_PROMO_DISCOUNTS[key] = {
                'key': key,
                'title': title,
                'target_type': target_type,
                'target_id': target_id,
                'target_name': target_name,
                'percent': percent,
                'start_date': start_dt,
                'end_date': end_dt,
                'created_by': request.user_account.employee.full_name,
            }
            messages.success(
                request,
                f'Акцію "{title}" (-{percent}% на {target_name}) активовано з {start_dt} по {end_dt}.'
            )
            return redirect('price_control')

        if action == 'remove_promo':
            promo_key = request.POST.get('promo_key')
            ACTIVE_PROMO_DISCOUNTS.pop(promo_key, None)
            messages.success(request, 'Акційну знижку скасовано.')
            return redirect('price_control')

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
            product.save(update_fields=['sale_price'])

        messages.success(request, f'Ціну на "{product.name}" змінено з {old_price} на {new_price} грн.')
        return redirect('price_control')

    date_from_str = (request.GET.get('date_from') or '').strip()
    date_to_str = (request.GET.get('date_to') or '').strip()
    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = date.fromisoformat(date_from_str)
    except ValueError:
        date_from_str = ''
    try:
        if date_to_str:
            date_to = date.fromisoformat(date_to_str)
    except ValueError:
        date_to_str = ''

    active_promos = list(ACTIVE_PROMO_DISCOUNTS.values())
    history_qs = PriceChange.objects.select_related('product', 'employee').order_by('-change_date', '-id')

    if date_from:
        history_qs = history_qs.filter(change_date__gte=date_from)
        active_promos = [p for p in active_promos if p['end_date'] >= date_from]
    if date_to:
        history_qs = history_qs.filter(change_date__lte=date_to)
        active_promos = [p for p in active_promos if p['start_date'] <= date_to]
    if not date_from and not date_to:
        history_qs = history_qs[:20]

    products = Product.objects.select_related('category').all()
    categories = ProductCategory.objects.all()
    return render(request, 'shared/prices.html', {
        'products': products,
        'categories': categories,
        'active_promos': active_promos,
        'history': history_qs,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'account': request.user_account
    })