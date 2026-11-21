from datetime import date, datetime
from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField

from ..models import Customer, Sale, SaleItem, ReturnProduct

ALLOWED_DISCOUNTS = {Decimal('3.00'), Decimal('5.00'), Decimal('10.00')}

ACTIVE_PROMO_DISCOUNTS = {}


def get_active_promo_for_product(product):
    today = date.today()
    best_promo = Decimal('0.00')
    expired_keys = []

    for key, promo in ACTIVE_PROMO_DISCOUNTS.items():
        if promo['end_date'] < today:
            expired_keys.append(key)
            continue
        if promo['start_date'] <= today <= promo['end_date']:
            if promo['target_type'] == 'category' and promo['target_id'] == product.category_id:
                best_promo = max(best_promo, promo['percent'])
            elif promo['target_type'] == 'product' and promo['target_id'] == product.id:
                best_promo = max(best_promo, promo['percent'])

    for key in expired_keys:
        ACTIVE_PROMO_DISCOUNTS.pop(key, None)

    return best_promo


def calculate_returns_sum(queryset):
    expr = ExpressionWrapper(
        F('sale_item__sale_price') * F('quantity') * (Decimal('100') - F('sale_item__discount')) / Decimal('100'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    total = queryset.aggregate(total_ret=Sum(expr))['total_ret'] or Decimal('0.00')
    return round(total, 2)


def get_customer_net_spent(customer):
    if not customer:
        return Decimal('0.00')

    total_sales = Sale.objects.filter(customer=customer).aggregate(
        total=Sum('total')
    )['total'] or Decimal('0.00')

    total_returns = calculate_returns_sum(
        ReturnProduct.objects.filter(sale_item__receipt__customer=customer)
    )

    return max(Decimal('0.00'), total_sales - total_returns)


def get_customer_discount(customer, strict_by_spent=False):
    if not customer:
        return Decimal('0.00')

    net_spent = get_customer_net_spent(customer)

    if net_spent >= Decimal('15000.00'):
        calculated_discount = Decimal('10.00')
    elif net_spent >= Decimal('5000.00'):
        calculated_discount = Decimal('5.00')
    else:
        calculated_discount = Decimal('3.00')

    if not strict_by_spent and customer.discount_percent in ALLOWED_DISCOUNTS:
        return max(customer.discount_percent, calculated_discount)

    return calculated_discount


def sync_all_customers_and_sales():
    customers = list(Customer.objects.all().order_by('-id'))
    for customer in customers:
        customer.net_spent = get_customer_net_spent(customer)
        actual_discount = get_customer_discount(customer)
        if customer.discount_percent != actual_discount:
            customer.discount_percent = actual_discount
            customer.save(update_fields=['discount_percent'])

    for item in SaleItem.objects.select_related('receipt__customer').filter(receipt__customer__isnull=False):
        target_discount = item.receipt.customer.discount_percent
        if item.discount != target_discount:
            item.discount = target_discount
            item.save(update_fields=['discount'])

    return customers


def build_shift_report(shift):
    end_dt = shift.close_time or datetime.now()
    shift_sales = Sale.objects.filter(
        employee=shift.employee,
        date__range=[shift.open_time.date(), end_dt.date()]
    )
    matched_sales = [
        s for s in shift_sales
        if shift.open_time <= datetime.combine(s.date, s.time) <= end_dt
    ]
    matched_sale_ids = [s.id for s in matched_sales]

    cash_sales = sum((s.total for s in matched_sales if s.payment_method == 'готівка'), Decimal('0.00'))
    card_sales = sum((s.total for s in matched_sales if s.payment_method != 'готівка'), Decimal('0.00'))

    returns_qs = ReturnProduct.objects.filter(
        employee=shift.employee,
        date__range=[shift.open_time.date(), end_dt.date()]
    )
    if shift.open_time.date() == end_dt.date():
        returns_sum = calculate_returns_sum(returns_qs)
    else:
        returns_sum = calculate_returns_sum(returns_qs.filter(sale_item__receipt_id__in=matched_sale_ids))

    expected_cash = shift.cash_start + cash_sales - returns_sum

    return {
        'shift': shift,
        'receipts_count': len(matched_sales),
        'cash_sales': cash_sales,
        'card_sales': card_sales,
        'returns_sum': returns_sum,
        'net_revenue': cash_sales + card_sales - returns_sum,
        'expected_cash': max(Decimal('0.00'), expected_cash),
        'generated_at': datetime.now(),
    }