from django.contrib import admin
from django.urls import path
from pet_store_project import views
from .views.shop import shop_catalog, shop_cart_action, shop_checkout, shop_my_orders
from .views.cashier import manage_online_orders

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
    path('director/analytics/', views.director_analytics, name='director_analytics'),

    path('cashier/', views.cashier_dashboard, name='cashier_dashboard'),
    path('cashier/shift/', views.shift_manage, name='shift_manage'),
    path('cashier/shift/x-report/', views.shift_x_report, name='shift_x_report'),
    path('cashier/sale/new/', views.create_sale, name='create_sale'),
    path('cashier/return/', views.process_return, name='process_return'),
    path('cashier/customers/', views.manage_customers, name='manage_customers'),
    path('cashier/goods-receipts/', views.goods_receipt_create, name='goods_receipt_create'),

    path('prices/', views.price_control, name='price_control'),

    path('manager/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/catalog/', views.manager_catalog, name='manager_catalog'),
    path('manager/inventory/', views.manager_inventory, name='manager_inventory'),
    path('manager/transfers/', views.manager_transfers, name='manager_transfers'),
    path('manager/write-offs/', views.manager_write_offs, name='manager_write_offs'),
    path('manager/suppliers/', views.manager_suppliers, name='manager_suppliers'),

    path('accountant/', views.accountant_dashboard, name='accountant_dashboard'),
    path('accountant/supplier-payments/', views.accountant_supplier_payments, name='accountant_supplier_payments'),
    path('accountant/salaries/', views.accountant_salaries, name='accountant_salaries'),
    path('accountant/pnl/', views.accountant_pnl_report, name='accountant_pnl_report'),

# Інтернет-магазин (вітрина для клієнтів)
    path('shop/', shop_catalog, name='shop_catalog'),
    path('shop/cart/', shop_cart_action, name='shop_cart_action'),
    path('shop/checkout/', shop_checkout, name='shop_checkout'),
    path('shop/orders/', shop_my_orders, name='shop_my_orders'),

    # Інтернет-замовлення для персоналу
    path('cashier/online-orders/', manage_online_orders, name='manage_online_orders'),
]