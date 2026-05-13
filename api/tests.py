from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Invoice, Product


class CheckoutViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='pass12345')
        self.product = Product.objects.create(
            name='Phone Charger',
            buying_price=Decimal('500.00'),
            price=Decimal('750.00'),
            stock=5,
            created_by=self.user,
        )
        self.client.force_authenticate(self.user)

    def test_checkout_accepts_flutter_product_key(self):
        response = self.client.post(
            reverse('pos_checkout'),
            {
                'items': [
                    {
                        'product': self.product.id,
                        'quantity': 2,
                        'discount': '50.00',
                    }
                ],
                'payment_method': 'Cash',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invoice = Invoice.objects.get(id=response.data['id'])
        self.product.refresh_from_db()

        self.assertEqual(invoice.total_amount, Decimal('1450.00'))
        self.assertEqual(invoice.total_discount, Decimal('50.00'))
        self.assertEqual(self.product.stock, 3)

    def test_checkout_returns_400_for_missing_product_id(self):
        response = self.client.post(
            reverse('pos_checkout'),
            {'items': [{'quantity': 1}], 'payment_method': 'Cash'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Invoice.objects.count(), 0)
