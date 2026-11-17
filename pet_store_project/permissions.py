from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from .models import UserAccount


def get_current_account(request):
    account_id = request.session.get('user_account_id')
    if not account_id:
        return None
    return UserAccount.objects.select_related('employee', 'role').filter(id=account_id, is_active=True).first()


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            account = get_current_account(request)
            if not account:
                return redirect('login')
            if account.role.name not in allowed_roles:
                raise PermissionDenied("У вас немає доступу до цього розділу.")
            request.user_account = account
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator