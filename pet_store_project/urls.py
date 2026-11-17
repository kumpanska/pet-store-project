from django.contrib import admin
from django.urls import path
from pet_store_project import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('director/', views.director_dashboard, name='director_dashboard'),
    path('director/employees/', views.director_employees, name='director_employees'),
    path('director/stores/', views.director_stores, name='director_stores'),
    path('director/salaries/', views.director_salaries_view, name='director_salaries'),
    path('cashier/', views.cashier_dashboard, name='cashier_dashboard'),
    path('cashier/shift/', views.shift_manage, name='shift_manage'),
    path('cashier/sale/new/', views.create_sale, name='create_sale'),
    path('cashier/return/', views.process_return, name='process_return'),
    path('cashier/customers/', views.manage_customers, name='manage_customers'),
    path('prices/', views.price_control, name='price_control'),
]