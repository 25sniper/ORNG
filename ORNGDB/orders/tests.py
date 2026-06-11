from django.test import TestCase, Client
from django.urls import reverse
from users.models import User
from products.models import Product
from orders.models import CartItem

class CartUpdateQtyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user(
            username='9876543210',
            password='password123',
            phone='9876543210',
            role='customer',
            name='Test Customer'
        )
        self.product = Product.objects.create(
            name='Apple',
            price=150.00,
            available=True
        )

    def test_cart_update_qty_requires_login(self):
        # Without login, should redirect to login
        url = reverse('cart_update_qty', args=[self.product.id])
        response = self.client.post(url, {'action': 'increase'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    def test_cart_update_qty_increase(self):
        self.client.login(username='9876543210', password='password123')
        url = reverse('cart_update_qty', args=[self.product.id])
        
        # Initially no cart item
        self.assertFalse(CartItem.objects.filter(customer=self.customer, product=self.product).exists())
        
        # Increase once
        response = self.client.post(url, {'action': 'increase'})
        self.assertRedirects(response, reverse('customer_menu'))
        
        cart_item = CartItem.objects.get(customer=self.customer, product=self.product)
        self.assertEqual(cart_item.quantity, 1)

        # Increase again
        response = self.client.post(url, {'action': 'increase'})
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 2)

    def test_cart_update_qty_decrease_and_delete(self):
        self.client.login(username='9876543210', password='password123')
        url = reverse('cart_update_qty', args=[self.product.id])
        
        # Create initial cart item with quantity 2
        cart_item = CartItem.objects.create(customer=self.customer, product=self.product, quantity=2)
        
        # Decrease once (qty goes to 1)
        response = self.client.post(url, {'action': 'decrease'})
        self.assertRedirects(response, reverse('customer_menu'))
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 1)
        
        # Decrease again (qty goes to 0, item deleted)
        response = self.client.post(url, {'action': 'decrease'})
        self.assertRedirects(response, reverse('customer_menu'))
        self.assertFalse(CartItem.objects.filter(customer=self.customer, product=self.product).exists())


class OrderAutoAssignmentTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='9876543210',
            password='password123',
            phone='9876543210',
            role='customer',
            name='Test Customer'
        )
        self.delivery1 = User.objects.create_user(
            username='delivery1',
            password='deliverypassword',
            role='delivery',
            name='Delivery Guy 1'
        )
        self.delivery2 = User.objects.create_user(
            username='delivery2',
            password='deliverypassword',
            role='delivery',
            name='Delivery Guy 2'
        )

    def test_order_auto_assigns_to_delivery1(self):
        from orders.models import Order
        order = Order.objects.create(
            customer=self.customer,
            total_amount=100.00
        )
        self.assertEqual(order.assigned_delivery_user, self.delivery1)

    def test_order_does_not_overwrite_explicit_assignment(self):
        from orders.models import Order
        order = Order.objects.create(
            customer=self.customer,
            total_amount=100.00,
            assigned_delivery_user=self.delivery2
        )
        self.assertEqual(order.assigned_delivery_user, self.delivery2)

    def test_order_fallback_assignment(self):
        self.delivery1.delete()
        from orders.models import Order
        order = Order.objects.create(
            customer=self.customer,
            total_amount=100.00
        )
        self.assertEqual(order.assigned_delivery_user, self.delivery2)


class ShareOrderBillTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='adminuser',
            password='password123',
            phone='9999999999',
            role='admin',
            name='Test Admin'
        )
        self.customer = User.objects.create_user(
            username='9876543210',
            password='password123',
            phone='9876543210',
            role='customer',
            name='Test Customer'
        )
        self.product = Product.objects.create(
            name='Fresh Mango Juice Special Pack',
            price=120.00,
            available=True
        )
        # Import Order & OrderItem
        from orders.models import Order, OrderItem
        self.order = Order.objects.create(
            customer=self.customer,
            total_amount=240.00,
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            price_at_time=120.00
        )

    def test_share_order_bill_format(self):
        self.client.login(username='adminuser', password='password123')
        url = reverse('share_order_bill', args=[self.order.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        bill_text = data['bill_text']
        
        # Check that all lines are exactly 32 characters long
        lines = bill_text.split('\n')
        for idx, line in enumerate(lines):
            self.assertEqual(len(line), 32, f"Line {idx} '{line}' is {len(line)} chars instead of 32")



