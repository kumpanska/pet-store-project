from .auth import register_view, login_view, logout_view
from .director import (
    director_dashboard,
    director_employees,
    director_stores,
    director_salaries_view,
    director_analytics,
)
from .cashier import (
    cashier_dashboard,
    shift_manage,
    shift_x_report,
    create_sale,
    process_return,
    manage_customers,
    goods_receipt_create,
)
from .manager import (
    manager_dashboard,
    manager_catalog,
    manager_inventory,
    manager_transfers,
    manager_write_offs,
    manager_suppliers,
)
from .accountant import (
    accountant_dashboard,
    accountant_supplier_payments,
    accountant_salaries,
    accountant_pnl_report,
)
from .shared import price_control