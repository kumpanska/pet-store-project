from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.contrib import messages

from ..models import (
    Employee, Sale, SaleItem, ReturnProduct, Salary,
    GoodsReceipt, SupplierPayment, WriteOffItem, WorkShift
)
from ..permissions import role_required
from .helpers import calculate_returns_sum


@role_required(['бухгалтер'])
def accountant_dashboard(request):
    today = date.today()
    month_sales = Sale.objects.filter(date__year=today.year, date__month=today.month).aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    month_returns = calculate_returns_sum(ReturnProduct.objects.filter(date__year=today.year, date__month=today.month))

    receipts = GoodsReceipt.objects.all()
    total_payable = sum((max(Decimal('0.00'), r.total - r.discrepancy_amount) for r in receipts), Decimal('0.00'))
    total_paid = SupplierPayment.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    debt_to_suppliers = max(Decimal('0.00'), total_payable - total_paid)

    return render(request, 'accountant/dashboard.html', {
        'account': request.user_account,
        'month_net_revenue': month_sales - month_returns,
        'debt_to_suppliers': debt_to_suppliers,
        'recent_payments': SupplierPayment.objects.select_related('supplier', 'goods_receipt').order_by('-date', '-id')[:10],
        'recent_salaries': Salary.objects.select_related('employee').order_by('-period_month')[:10],
    })


@role_required(['бухгалтер'])
def accountant_supplier_payments(request):
    if request.method == 'POST':
        receipt = get_object_or_404(GoodsReceipt, id=request.POST.get('goods_receipt_id'))
        payment_method = request.POST.get('payment_method', 'безготівковий')
        note = (request.POST.get('note') or '').strip()

        try:
            amount = Decimal(request.POST.get('amount', '0'))
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, 'Введіть коректну суму оплати.')
            return redirect('accountant_supplier_payments')

        paid_already = SupplierPayment.objects.filter(goods_receipt=receipt).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        net_invoice_total = max(Decimal('0.00'), receipt.total - receipt.discrepancy_amount)
        remaining = net_invoice_total - paid_already

        if amount > remaining:
            messages.error(request, f'Сума оплати перевищує залишок боргу з урахуванням акту розбіжностей ({remaining} грн).')
            return redirect('accountant_supplier_payments')

        SupplierPayment.objects.create(
            supplier=receipt.supplier,
            goods_receipt=receipt,
            date=date.today(),
            amount=amount,
            payment_method=payment_method,
            note=note or None
        )
        messages.success(
            request,
            f'Оплату {amount} грн ({payment_method}) по накладній №{receipt.id} ({receipt.supplier.company_name}) проведено.'
        )
        return redirect('accountant_supplier_payments')

    receipts = list(GoodsReceipt.objects.select_related('supplier', 'verified_by').order_by('-date', '-id'))
    for r in receipts:
        paid = SupplierPayment.objects.filter(goods_receipt=r).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        net_total = max(Decimal('0.00'), r.total - r.discrepancy_amount)
        r.paid_amount = paid
        r.net_total = net_total
        r.balance_due = max(Decimal('0.00'), net_total - paid)

    payments = SupplierPayment.objects.select_related('supplier', 'goods_receipt').order_by('-date', '-id')[:30]
    return render(request, 'accountant/supplier_payments.html', {
        'account': request.user_account,
        'receipts': receipts,
        'payments': payments,
    })


@role_required(['бухгалтер'])
def accountant_salaries(request):
    today = date.today()

    if request.method == 'POST':
        emp = get_object_or_404(Employee, id=request.POST.get('employee_id'))
        period_str = request.POST.get('period_month')
        try:
            if len(period_str) == 7:
                period_date = datetime.strptime(period_str + '-01', '%Y-%m-%d').date()
            else:
                period_date = datetime.strptime(period_str, '%Y-%m-%d').date().replace(day=1)

            base_amount = Decimal(request.POST.get('base_amount', '0'))
            auto_bonus_pct = Decimal(request.POST.get('sales_bonus_percent', '0'))
            manual_bonus = Decimal(request.POST.get('manual_bonus', '0'))

            if base_amount < 0 or auto_bonus_pct < 0 or manual_bonus < 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, 'Перевірте коректність введених сум та періоду.')
            return redirect('accountant_salaries')

        emp_sales = Sale.objects.filter(
            employee=emp,
            date__year=period_date.year,
            date__month=period_date.month
        ).aggregate(s=Sum('total'))['s'] or Decimal('0.00')

        calculated_bonus = round((emp_sales * auto_bonus_pct / Decimal('100')) + manual_bonus, 2)

        Salary.objects.create(
            employee=emp,
            period_month=period_date,
            base_amount=base_amount,
            bonus=calculated_bonus
        )
        messages.success(
            request,
            f'Зарплату для {emp.full_name} за {period_date.strftime("%m.%Y")} нараховано '
            f'(ставка: {base_amount} грн + премія: {calculated_bonus} грн).'
        )
        return redirect('accountant_salaries')

    employees = list(Employee.objects.select_related('store').all())
    for emp in employees:
        emp.month_shifts_count = WorkShift.objects.filter(
            employee=emp, open_time__year=today.year, open_time__month=today.month
        ).count()
        emp.month_sales_sum = Sale.objects.filter(
            employee=emp, date__year=today.year, date__month=today.month
        ).aggregate(s=Sum('total'))['s'] or Decimal('0.00')

    salaries = Salary.objects.select_related('employee__store').order_by('-period_month', 'employee__full_name')
    return render(request, 'accountant/salaries.html', {
        'account': request.user_account,
        'employees': employees,
        'salaries': salaries,
        'current_month': today.strftime('%Y-%m'),
    })


@role_required(['бухгалтер'])
def accountant_pnl_report(request):
    today = date.today()
    date_from_str = request.GET.get('date_from') or today.replace(day=1).isoformat()
    date_to_str = request.GET.get('date_to') or today.isoformat()

    gross_sales = Sale.objects.filter(date__range=[date_from_str, date_to_str]).aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    returns_sum = calculate_returns_sum(ReturnProduct.objects.filter(date__range=[date_from_str, date_to_str]))
    net_revenue = gross_sales - returns_sum

    cogs_expr = ExpressionWrapper(
        F('product__purchase_price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    cogs = SaleItem.objects.filter(receipt__date__range=[date_from_str, date_to_str]).aggregate(s=Sum(cogs_expr))['s'] or Decimal('0.00')

    write_off_expr = ExpressionWrapper(
        F('product__purchase_price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    write_offs_loss = WriteOffItem.objects.filter(write_off_act__date__range=[date_from_str, date_to_str]).aggregate(s=Sum(write_off_expr))['s'] or Decimal('0.00')

    payroll_expenses = Salary.objects.filter(period_month__range=[date_from_str, date_to_str]).aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    purchases_total = GoodsReceipt.objects.filter(date__range=[date_from_str, date_to_str]).aggregate(s=Sum('total'))['s'] or Decimal('0.00')

    gross_profit = net_revenue - cogs
    net_profit = gross_profit - payroll_expenses - write_offs_loss

    return render(request, 'accountant/pnl_report.html', {
        'account': request.user_account,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'gross_sales': gross_sales,
        'returns_sum': returns_sum,
        'net_revenue': net_revenue,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'payroll_expenses': payroll_expenses,
        'write_offs_loss': write_offs_loss,
        'purchases_total': purchases_total,
        'net_profit': net_profit,
    })