"""
URL configuration for pet_store_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from . import views

urlpatterns = [
    # Авторизація
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Блок Директора
    path('director/', views.director_dashboard, name='director_dashboard'),
    path('director/employees/', views.director_employees, name='director_employees'),
    path('director/stores/', views.director_stores, name='director_stores'),
    path('director/salaries/', views.director_salaries_view, name='director_salaries'),

    # Блок Продавця-консультанта
    path('cashier/', views.cashier_dashboard, name='cashier_dashboard'),
    path('cashier/shift/', views.shift_manage, name='shift_manage'),
    path('cashier/sale/new/', views.create_sale, name='create_sale'),
    path('cashier/return/', views.process_return, name='process_return'),
    path('cashier/customers/', views.manage_customers, name='manage_customers'),

    # Спільний блок (Продавець-консультант + Менеджер)
    path('prices/', views.price_control, name='price_control'),
]
