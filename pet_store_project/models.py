from django.db import models
from django.db.models import F, ExpressionWrapper, DecimalField


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'product_category'

    def __str__(self):
        return self.name


class Supplier(models.Model):
    company_name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.CharField(max_length=100, unique=True)

    class Meta:
        managed = False
        db_table = 'supplier'

    def __str__(self):
        return self.company_name


class Customer(models.Model):
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    email = models.CharField(max_length=100, unique=True, blank=True, null=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        managed = False
        db_table = 'customer'

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class Store(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'store'

    def __str__(self):
        return f"{self.name} ({self.type})"


class Employee(models.Model):
    full_name = models.CharField(max_length=150)
    position = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, db_column='store_id')

    class Meta:
        managed = False
        db_table = 'employee'

    def __str__(self):
        return self.full_name


class RoleInStore(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'role_in_store'

    def __str__(self):
        return self.name


class UserAccount(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, db_column='employee_id')
    login = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=255)
    role = models.ForeignKey(RoleInStore, on_delete=models.PROTECT, db_column='role_id')
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'user_account'

    def __str__(self):
        return f"{self.login} - {self.role.name}"


class Product(models.Model):
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=20, unique=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    expiration_date = models.DateField(blank=True, null=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, db_column='category_id')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column='supplier_id')

    class Meta:
        managed = False
        db_table = 'product'

    def __str__(self):
        return f"{self.name} [{self.barcode}]"


class Sale(models.Model):
    date = models.DateField()
    time = models.TimeField()
    payment_method = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, db_column='customer_id')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')

    class Meta:
        managed = False
        db_table = 'sale'


class SaleItem(models.Model):
    receipt = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', db_column='receipt_id')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    quantity = models.IntegerField()
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        managed = False
        db_table = 'sale_item'


class ReturnProduct(models.Model):
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, db_column='sale_item_id')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')
    date = models.DateField()
    quantity = models.IntegerField()
    reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'return_product'


class WorkShift(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')
    open_time = models.DateTimeField()
    close_time = models.DateTimeField(null=True, blank=True)
    cash_start = models.DecimalField(max_digits=12, decimal_places=2)
    cash_end = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        managed = False
        db_table = 'work_shift'


class PriceChange(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, db_column='product_id')
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    change_date = models.DateField()
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')

    class Meta:
        managed = False
        db_table = 'price_change'


class Salary(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, db_column='employee_id')
    period_month = models.DateField()
    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.GeneratedField(
        expression=ExpressionWrapper(
            F('base_amount') + F('bonus'),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        ),
        output_field=DecimalField(max_digits=10, decimal_places=2),
        db_persist=True,
    )

    class Meta:
        managed = False
        db_table = 'salary'


class GoodsReceipt(models.Model):
    date = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column='supplier_id')
    is_verified = models.BooleanField(default=False)
    manager_note = models.TextField(blank=True, null=True)
    discrepancy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    verified_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, db_column='verified_by_id')

    class Meta:
        managed = False
        db_table = 'goods_receipt'


class GoodsReceiptItem(models.Model):
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items', db_column='goods_receipt_id')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    quantity = models.IntegerField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.GeneratedField(
        expression=ExpressionWrapper(
            F('quantity') * F('purchase_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        ),
        output_field=DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )

    class Meta:
        managed = False
        db_table = 'goods_receipt_item'


class InventoryCheck(models.Model):
    date = models.DateField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    expected_quantity = models.IntegerField()
    actual_quantity = models.IntegerField()
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')

    class Meta:
        managed = False
        db_table = 'inventory_check'


class StockTransfer(models.Model):
    date = models.DateField()
    from_store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='transfers_out', db_column='from_store_id')
    to_store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='transfers_in', db_column='to_store_id')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    quantity = models.IntegerField()
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')

    class Meta:
        managed = False
        db_table = 'stock_transfer'


class WriteOffAct(models.Model):
    date = models.DateField()
    reason = models.CharField(max_length=255)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, db_column='employee_id')

    class Meta:
        managed = False
        db_table = 'write_off_act'


class WriteOffItem(models.Model):
    write_off_act = models.ForeignKey(WriteOffAct, on_delete=models.CASCADE, related_name='items', db_column='write_off_act_id')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    quantity = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'write_off_item'


class SupplierOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column='supplier_id')
    date = models.DateField()
    status = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'supplier_order'


class SupplierOrderItem(models.Model):
    supplier_order = models.ForeignKey(SupplierOrder, on_delete=models.CASCADE, related_name='items', db_column='supplier_order_id')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='product_id')
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'supplier_order_item'


class SupplierPayment(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_column='supplier_id')
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, db_column='goods_receipt_id')
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=30, default='безготівковий')
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'supplier_payment'