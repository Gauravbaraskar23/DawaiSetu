"""
DawaiSetu — Automated Test Suite
==================================
Place this file as store/tests.py (or any single app's tests.py).
It imports models/views across accounts, store, subscriptions, orders,
and notifications apps — Django will discover and run it regardless
of which app folder it lives in, as long as that app is in INSTALLED_APPS.

Run with:
    python manage.py test
or, if using pytest-django:
    pytest
"""

from io import StringIO

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core import mail
from django.core.management import call_command
from datetime import timedelta

from store.models import Medicine, Category, SubCategory, Manufacturer, Molecule, StoreVisit
from subscriptions.models import SubscriptionPlan, UserSubscription, StoreProfile
from orders.models import Order, OrderItem
from notifications.models import Notification


User = get_user_model()


# =====================================================================
# HELPERS — shared factory functions to avoid repeating setup everywhere
# =====================================================================

def make_plan(**kwargs):
    defaults = dict(
        name='Test Plan',
        price=0,
        duration_days=30,
        max_medicines=50,
        allow_custom_link=False,
        has_analytics_dashboard=False,
        has_stock_alerts=False,
        can_export_data=False,
        max_staff_accounts=0,
        has_custom_domain=False,
    )
    defaults.update(kwargs)
    return SubscriptionPlan.objects.create(**defaults)


def give_active_subscription(user, plan, days_left=30):
    return UserSubscription.objects.create(
        user=user,
        plan=plan,
        is_active=True,
        end_date=timezone.now() + timedelta(days=days_left),
    )


def make_medicine_prereqs():
    category = Category.objects.create(name='Painkillers')
    subcategory = SubCategory.objects.create(category=category, name='Tablets')
    manufacturer = Manufacturer.objects.create(name='Test Pharma Ltd')
    molecule = Molecule.objects.create(name='Paracetamol')
    return subcategory, manufacturer, molecule


def make_medicine(seller, **kwargs):
    subcategory, manufacturer, molecule = make_medicine_prereqs()
    defaults = dict(
        seller=seller,
        name='Test Medicine',
        subcategory=subcategory,
        manufacturer=manufacturer,
        molecule=molecule,
        composition='Test Composition',
        actual_price=100,
        description='Test description',
        stock_available=20,
        is_available=True,
    )
    defaults.update(kwargs)
    return Medicine.objects.create(**defaults)


# =====================================================================
# 1. USER MODEL PROPERTIES — effective_seller, permissions
# =====================================================================

class UserModelPropertyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner1', password='pass123', is_store_staff=True, agency_name='Owner Pharmacy'
        )
        self.order_staff = User.objects.create_user(
            username='order_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='order_manager'
        )
        self.inventory_staff = User.objects.create_user(
            username='inv_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='inventory_manager'
        )
        self.full_access_staff = User.objects.create_user(
            username='full_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='full_access'
        )

    def test_owner_effective_seller_is_self(self):
        self.assertEqual(self.owner.effective_seller, self.owner)
        self.assertFalse(self.owner.is_staff_member)

    def test_staff_effective_seller_is_owner(self):
        self.assertEqual(self.order_staff.effective_seller, self.owner)
        self.assertEqual(self.inventory_staff.effective_seller, self.owner)
        self.assertTrue(self.order_staff.is_staff_member)

    def test_order_manager_permissions(self):
        self.assertTrue(self.order_staff.can_manage_orders)
        self.assertFalse(self.order_staff.can_manage_inventory)

    def test_inventory_manager_permissions(self):
        self.assertTrue(self.inventory_staff.can_manage_inventory)
        self.assertFalse(self.inventory_staff.can_manage_orders)

    def test_full_access_permissions(self):
        self.assertTrue(self.full_access_staff.can_manage_orders)
        self.assertTrue(self.full_access_staff.can_manage_inventory)

    def test_owner_always_has_full_permissions(self):
        self.assertTrue(self.owner.can_manage_orders)
        self.assertTrue(self.owner.can_manage_inventory)


# =====================================================================
# 2. SIGNUP / LOGIN FLOW
# =====================================================================

class SignupLoginTests(TestCase):
    def test_seller_signup_sets_is_store_staff(self):
        self.client.post(reverse('signup'), {
            'username': 'newseller',
            'email': 'newseller@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'role': 'seller',
            'agency_name': 'New Pharmacy',
        })
        user = User.objects.get(username='newseller')
        self.assertTrue(user.is_store_staff)
        self.assertEqual(user.agency_name, 'New Pharmacy')

    def test_customer_signup_does_not_set_is_store_staff(self):
        self.client.post(reverse('signup'), {
            'username': 'newcustomer',
            'email': 'newcustomer@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'role': 'customer',
        })
        user = User.objects.get(username='newcustomer')
        self.assertFalse(user.is_store_staff)

    def test_duplicate_email_signup_rejected(self):
        User.objects.create_user(username='existing', email='dup@test.com', password='pass123')
        response = self.client.post(reverse('signup'), {
            'username': 'another',
            'email': 'dup@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'role': 'customer',
        })
        self.assertFalse(User.objects.filter(username='another').exists())

    def test_seller_login_redirects_to_dashboard(self):
        User.objects.create_user(username='sellerlogin', password='pass123', is_store_staff=True)
        response = self.client.post(reverse('login'), {
            'username': 'sellerlogin', 'password': 'pass123'
        })
        self.assertRedirects(response, '/dashboard/')

    def test_customer_login_redirects_to_home(self):
        User.objects.create_user(username='customerlogin', password='pass123')
        response = self.client.post(reverse('login'), {
            'username': 'customerlogin', 'password': 'pass123'
        })
        self.assertRedirects(response, '/')


# =====================================================================
# 3. MULTIPLE SUBSCRIPTIONS — the core bug we fixed
# =====================================================================

class MultiplePlansTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='multiplan_seller', password='pass123', is_store_staff=True)
        self.plan_base = make_plan(name='Base Plan', max_medicines=50, allow_custom_link=True)
        self.plan_export = make_plan(name='Export Add-on', max_medicines=10, can_export_data=True)
        self.plan_unlimited = make_plan(name='Unlimited Plan', max_medicines=-1, has_custom_domain=True)

    def test_buying_second_plan_keeps_first(self):
        give_active_subscription(self.seller, self.plan_base)
        give_active_subscription(self.seller, self.plan_export)
        self.assertEqual(self.seller.subscriptions.count(), 2)

    def test_features_combine_across_plans(self):
        give_active_subscription(self.seller, self.plan_base)
        give_active_subscription(self.seller, self.plan_export)
        features = self.seller.effective_plan_features
        self.assertTrue(features['allow_custom_link'])   # from plan_base
        self.assertTrue(features['can_export_data'])      # from plan_export
        self.assertEqual(features['max_medicines'], 50)   # max(50, 10)

    def test_unlimited_medicine_plan_overrides_limit(self):
        give_active_subscription(self.seller, self.plan_base)      # 50
        give_active_subscription(self.seller, self.plan_unlimited)  # -1 (unlimited)
        features = self.seller.effective_plan_features
        self.assertEqual(features['max_medicines'], -1)
        self.assertTrue(features['has_custom_domain'])

    def test_expired_plan_features_excluded(self):
        give_active_subscription(self.seller, self.plan_export, days_left=-5)  # already expired
        features = self.seller.effective_plan_features
        self.assertFalse(features['can_export_data'])

    def test_deactivated_plan_features_excluded(self):
        sub = give_active_subscription(self.seller, self.plan_export)
        sub.is_active = False
        sub.save()
        features = self.seller.effective_plan_features
        self.assertFalse(features['can_export_data'])

    def test_free_plan_checkout_creates_subscription_without_deleting_old(self):
        self.client.force_login(self.seller)
        give_active_subscription(self.seller, self.plan_base)

        self.client.get(reverse('checkout', args=[self.plan_export.id]) + '?type=inventory')

        self.assertEqual(self.seller.subscriptions.filter(is_active=True).count(), 2)

    def test_checkout_sends_activation_notification(self):
        self.client.force_login(self.seller)
        self.client.get(reverse('checkout', args=[self.plan_base.id]) + '?type=inventory')
        self.assertTrue(
            Notification.objects.filter(recipient=self.seller, title__icontains='Activated').exists()
        )

    def test_no_active_plan_returns_default_features(self):
        features = self.seller.effective_plan_features
        self.assertEqual(features['max_medicines'], 50)
        self.assertFalse(features['can_export_data'])
        self.assertFalse(features['allow_custom_link'])


# =====================================================================
# 4. INVENTORY PERMISSIONS — staff can/cannot manage medicines
# =====================================================================

class InventoryPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='inv_owner', password='pass123', is_store_staff=True)
        self.order_staff = User.objects.create_user(
            username='inv_order_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='order_manager'
        )
        self.inventory_staff = User.objects.create_user(
            username='inv_inventory_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='inventory_manager'
        )
        plan = make_plan(name='Big Plan', max_medicines=100)
        give_active_subscription(self.owner, plan)

    def test_order_manager_blocked_from_add_medicine(self):
        self.client.force_login(self.order_staff)
        response = self.client.get(reverse('add_medicine'))
        self.assertRedirects(response, reverse('seller_dashboard'))

    def test_inventory_manager_can_access_add_medicine(self):
        self.client.force_login(self.inventory_staff)
        response = self.client.get(reverse('add_medicine'))
        self.assertEqual(response.status_code, 200)

    def test_medicine_added_by_staff_belongs_to_owner(self):
        subcategory, manufacturer, molecule = make_medicine_prereqs()
        self.client.force_login(self.inventory_staff)
        self.client.post(reverse('add_medicine'), {
            'name': 'Staff Added Medicine',
            'subcategory': subcategory.id,
            'manufacturer': manufacturer.id,
            'molecule': molecule.id,
            'composition': 'Test',
            'actual_price': 50,
            'description': 'desc',
            'stock_available': 10,
        })
        medicine = Medicine.objects.filter(name='Staff Added Medicine').first()
        self.assertIsNotNone(medicine)
        self.assertEqual(medicine.seller, self.owner)  # NOT the staff account

    def test_staff_cannot_edit_others_medicine(self):
        other_seller = User.objects.create_user(username='other_seller', password='pass123', is_store_staff=True)
        medicine = make_medicine(seller=other_seller)
        self.client.force_login(self.inventory_staff)
        response = self.client.get(reverse('edit_medicine', args=[medicine.slug]))
        self.assertEqual(response.status_code, 404)

    def test_medicine_limit_enforced(self):
        low_plan = make_plan(name='Tiny Plan', max_medicines=1)
        seller = User.objects.create_user(username='limited_seller', password='pass123', is_store_staff=True)
        give_active_subscription(seller, low_plan)
        make_medicine(seller=seller)  # 1 medicine already exists

        subcategory, manufacturer, molecule = make_medicine_prereqs()
        self.client.force_login(seller)
        response = self.client.get(reverse('add_medicine'))
        # Should redirect to pricing since limit is reached
        self.client.post(reverse('add_medicine'), {
            'name': 'Second Medicine',
            'subcategory': subcategory.id,
            'manufacturer': manufacturer.id,
            'molecule': molecule.id,
            'composition': 'Test',
            'actual_price': 50,
            'description': 'desc',
            'stock_available': 10,
        })
        self.assertEqual(Medicine.objects.filter(seller=seller).count(), 1)  # still 1, second was blocked


# =====================================================================
# 5. ORDER PERMISSIONS — staff order management
# =====================================================================

class OrderPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='order_owner', password='pass123', is_store_staff=True)
        self.order_staff = User.objects.create_user(
            username='order_mgr_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='order_manager'
        )
        self.inventory_staff = User.objects.create_user(
            username='inv_mgr_staff', password='pass123', is_store_staff=True,
            parent_seller=self.owner, staff_role='inventory_manager'
        )
        self.customer = User.objects.create_user(username='order_customer', password='pass123')

        self.medicine = make_medicine(seller=self.owner)
        self.order = Order.objects.create(
            customer=self.customer,
            customer_phone='9999999999',
            seller=self.owner,
            delivery_address='Test Address',
            status='Pending',
        )
        OrderItem.objects.create(order=self.order, medicine=self.medicine, quantity=2, total_price=200)

    def test_order_manager_can_view_order(self):
        self.client.force_login(self.order_staff)
        response = self.client.get(reverse('order_detail', args=[self.order.id]))
        self.assertEqual(response.status_code, 200)

    def test_order_manager_can_update_status(self):
        self.client.force_login(self.order_staff)
        self.client.post(reverse('update_order_status', args=[self.order.id]), {'status': 'Processing'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Processing')

    def test_inventory_manager_cannot_update_order_status(self):
        self.client.force_login(self.inventory_staff)
        self.client.post(reverse('update_order_status', args=[self.order.id]), {'status': 'Processing'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Pending')  # unchanged

    def test_unrelated_seller_cannot_view_order(self):
        stranger = User.objects.create_user(username='stranger_seller', password='pass123', is_store_staff=True)
        self.client.force_login(stranger)
        response = self.client.get(reverse('order_detail', args=[self.order.id]))
        self.assertEqual(response.status_code, 403)

    def test_customer_can_view_own_order(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('order_detail', args=[self.order.id]))
        self.assertEqual(response.status_code, 200)

    def test_order_completed_notifies_customer(self):
        self.client.force_login(self.order_staff)
        self.client.post(reverse('update_order_status', args=[self.order.id]), {'status': 'Completed'})
        self.assertTrue(
            Notification.objects.filter(recipient=self.customer, notification_type='Order').exists()
        )


# =====================================================================
# 6. STAFF MANAGEMENT — creation limits & activation blocking
# =====================================================================

class StaffManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='staffmgmt_owner', password='pass123', is_store_staff=True)
        self.plan = make_plan(name='Staff Plan', max_staff_accounts=2)
        give_active_subscription(self.owner, self.plan)

    def test_can_create_staff_within_limit(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('manage_staff'), {
            'username': 'newstaffmember',
            'password': 'pass123',
            'staff_role': 'order_manager',
        })
        self.assertTrue(User.objects.filter(username='newstaffmember', parent_seller=self.owner).exists())

    def test_cannot_exceed_max_staff_accounts(self):
        User.objects.create_user(username='staff_a', password='pass123', is_store_staff=True,
                                  parent_seller=self.owner, staff_role='order_manager')
        User.objects.create_user(username='staff_b', password='pass123', is_store_staff=True,
                                  parent_seller=self.owner, staff_role='order_manager')
        # Plan only allows 2 — this third one should be rejected
        self.client.force_login(self.owner)
        self.client.post(reverse('manage_staff'), {
            'username': 'staff_c',
            'password': 'pass123',
            'staff_role': 'order_manager',
        })
        self.assertFalse(User.objects.filter(username='staff_c').exists())

    def test_staff_member_cannot_access_manage_staff(self):
        staff = User.objects.create_user(username='regular_staff', password='pass123', is_store_staff=True,
                                          parent_seller=self.owner, staff_role='order_manager')
        self.client.force_login(staff)
        response = self.client.get(reverse('manage_staff'))
        self.assertRedirects(response, reverse('seller_dashboard'))

    def test_owner_can_deactivate_staff(self):
        staff = User.objects.create_user(username='to_deactivate', password='pass123', is_store_staff=True,
                                          parent_seller=self.owner, staff_role='order_manager')
        self.client.force_login(self.owner)
        self.client.post(reverse('toggle_staff_status', args=[staff.id]))
        staff.refresh_from_db()
        self.assertFalse(staff.is_active)


# =====================================================================
# 7. EMAIL SENDING — feedback form & notifications
#    (Django auto-collects outgoing emails in mail.outbox during tests,
#    no real email is sent)
# =====================================================================

class EmailSendingTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username='feedback_user', password='pass123', email='fb@test.com')

    def test_feedback_form_sends_email(self):
        self.client.force_login(self.customer)
        self.client.post(reverse('submit_feedback'), {
            'subject': 'Technical Bug',
            'message': 'The stock update button is not working.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('stock update button', mail.outbox[0].body)
        self.assertIn('feedback_user', mail.outbox[0].body)

    def test_feedback_requires_ajax_header(self):
        self.client.force_login(self.customer)
        self.client.post(reverse('submit_feedback'), {
            'subject': 'Technical Bug',
            'message': 'No AJAX header sent',
        })
        self.assertEqual(len(mail.outbox), 0)


# =====================================================================
# 8. MANAGEMENT COMMANDS — expiry reminders & staff sync
# =====================================================================

class ManagementCommandTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='cmd_seller', password='pass123', is_store_staff=True)
        self.plan = make_plan(name='Expiring Plan', max_staff_accounts=1)

    def test_expiry_reminder_sent_for_plan_expiring_in_2_days(self):
        UserSubscription.objects.create(
            user=self.seller,
            plan=self.plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=2),
        )
        out = StringIO()
        call_command('send_expiry_reminders', stdout=out)

        self.assertIn('Sent 1', out.getvalue())
        self.assertTrue(
            Notification.objects.filter(recipient=self.seller, title__icontains='Expiring').exists()
        )

    def test_expiry_reminder_not_duplicated_on_second_run(self):
        UserSubscription.objects.create(
            user=self.seller,
            plan=self.plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=3),
        )
        call_command('send_expiry_reminders', stdout=StringIO())
        call_command('send_expiry_reminders', stdout=StringIO())  # run twice

        count = Notification.objects.filter(recipient=self.seller, title__icontains='Expiring').count()
        self.assertEqual(count, 1)  # should not duplicate

    def test_expiry_reminder_skips_plans_not_expiring_soon(self):
        UserSubscription.objects.create(
            user=self.seller,
            plan=self.plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=20),  # not within 2-3 day window
        )
        call_command('send_expiry_reminders', stdout=StringIO())
        self.assertFalse(
            Notification.objects.filter(recipient=self.seller, title__icontains='Expiring').exists()
        )

    def test_sync_staff_limits_deactivates_excess_staff(self):
        # Plan allows only 1 staff account
        give_active_subscription(self.seller, self.plan)
        staff1 = User.objects.create_user(username='sync_staff1', password='pass123', is_store_staff=True,
                                           parent_seller=self.seller, staff_role='order_manager', is_active=True)
        staff2 = User.objects.create_user(username='sync_staff2', password='pass123', is_store_staff=True,
                                           parent_seller=self.seller, staff_role='order_manager', is_active=True)

        call_command('sync_staff_limits', stdout=StringIO())

        active_count = self.seller.staff_members.filter(is_active=True).count()
        self.assertEqual(active_count, 1)  # only one should remain active


# =====================================================================
# 9. CART & CHECKOUT — customer purchase flow
# =====================================================================

class CartCheckoutTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='cart_seller', password='pass123', is_store_staff=True)
        self.customer = User.objects.create_user(username='cart_customer', password='pass123')
        self.medicine = make_medicine(seller=self.seller, stock_available=10, actual_price=50)

    def test_add_to_cart(self):
        self.client.force_login(self.customer)
        self.client.get(reverse('add_to_cart', args=[self.medicine.id]))
        self.assertTrue(self.customer.cart.items.filter(medicine=self.medicine).exists())

    def test_cart_checkout_creates_order_and_reduces_stock(self):
        self.client.force_login(self.customer)
        self.client.get(reverse('add_to_cart', args=[self.medicine.id]))
        self.client.post(reverse('cart_checkout'), {
            'address': 'Test Delivery Address',
            'phone': '9999999999',
        })
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.stock_available, 9)  # 10 - 1
        self.assertTrue(Order.objects.filter(customer=self.customer, seller=self.seller).exists())

    def test_cart_checkout_notifies_seller(self):
        self.client.force_login(self.customer)
        self.client.get(reverse('add_to_cart', args=[self.medicine.id]))
        self.client.post(reverse('cart_checkout'), {
            'address': 'Test Delivery Address',
            'phone': '9999999999',
        })
        self.assertTrue(
            Notification.objects.filter(recipient=self.seller, notification_type='Order').exists()
        )
    

# =====================================================================
# 10. STORE ANALYTICS — visit tracking & aggregation
# =====================================================================

class StoreAnalyticsTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='analytics_seller', password='pass123', is_store_staff=True)
        self.customer = User.objects.create_user(username='analytics_customer', password='pass123')
        self.medicine = make_medicine(seller=self.seller, actual_price=100, stock_available=50)

        self.plan_with_analytics = make_plan(name='Analytics Plan', has_analytics_dashboard=True)
        self.plan_without_analytics = make_plan(name='Basic Plan', has_analytics_dashboard=False)

    # ---------- VISIT TRACKING ----------

    def test_visiting_store_creates_a_visit_record(self):
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')
        self.assertEqual(StoreVisit.objects.filter(seller=self.seller).count(), 1)

    def test_repeat_visit_same_session_same_day_not_duplicated(self):
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')
        self.assertEqual(StoreVisit.objects.filter(seller=self.seller).count(), 1)

    def test_visit_from_different_session_counts_separately(self):
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')

        second_client = self.client_class()  # a fresh client = a fresh session
        second_client.get(reverse('home') + f'?seller_id={self.seller.id}')

        self.assertEqual(StoreVisit.objects.filter(seller=self.seller).count(), 2)

    def test_browsing_without_seller_id_does_not_create_visit(self):
        self.client.get(reverse('home'))
        self.assertEqual(StoreVisit.objects.count(), 0)

    # ---------- ACCESS CONTROL ----------

    def test_owner_can_access_analytics_page(self):
        give_active_subscription(self.seller, self.plan_with_analytics)
        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))
        self.assertEqual(response.status_code, 200)

    def test_staff_member_blocked_from_analytics(self):
        staff = User.objects.create_user(username='analytics_staff', password='pass123', is_store_staff=True,
                                          parent_seller=self.seller, staff_role='full_access')
        self.client.force_login(staff)
        response = self.client.get(reverse('store_analytics'))
        self.assertRedirects(response, reverse('seller_dashboard'))

    def test_no_analytics_plan_shows_upgrade_state(self):
        give_active_subscription(self.seller, self.plan_without_analytics)
        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))
        self.assertFalse(response.context['has_analytics'])

    def test_plan_with_analytics_shows_full_data(self):
        give_active_subscription(self.seller, self.plan_with_analytics)
        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))
        self.assertTrue(response.context['has_analytics'])
        self.assertIn('yearly_history', response.context)

    # ---------- DATA CORRECTNESS ----------

    def test_lifetime_totals_reflect_visits_and_orders(self):
        give_active_subscription(self.seller, self.plan_with_analytics)

        # 2 visits (different sessions)
        self.client.get(reverse('home') + f'?seller_id={self.seller.id}')
        second_client = self.client_class()
        second_client.get(reverse('home') + f'?seller_id={self.seller.id}')

        # 1 order
        order = Order.objects.create(
            customer=self.customer, customer_phone='9999999999', seller=self.seller,
            delivery_address='Test Address', status='Completed'
        )
        OrderItem.objects.create(order=order, medicine=self.medicine, quantity=1, total_price=100)

        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))

        self.assertEqual(response.context['total_visits_lifetime'], 2)
        self.assertEqual(response.context['total_orders_lifetime'], 1)
        self.assertEqual(response.context['total_sales_lifetime'], 100)

    def test_cancelled_orders_excluded_from_sales(self):
        give_active_subscription(self.seller, self.plan_with_analytics)

        order = Order.objects.create(
            customer=self.customer, customer_phone='9999999999', seller=self.seller,
            delivery_address='Test Address', status='Cancelled'
        )
        OrderItem.objects.create(order=order, medicine=self.medicine, quantity=1, total_price=100)

        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))

        self.assertEqual(response.context['total_sales_lifetime'], 0)
        self.assertEqual(response.context['total_orders_lifetime'], 0)

    def test_best_year_reflects_highest_sales(self):
        give_active_subscription(self.seller, self.plan_with_analytics)

        now = timezone.now()

        # Two orders in the current year (small sales)
        order1 = Order.objects.create(
            customer=self.customer, customer_phone='9999999999', seller=self.seller,
            delivery_address='Addr', status='Completed'
        )
        OrderItem.objects.create(order=order1, medicine=self.medicine, quantity=1, total_price=50)

        # One order last year, backdated, with much bigger sales
        order2 = Order.objects.create(
            customer=self.customer, customer_phone='9999999999', seller=self.seller,
            delivery_address='Addr', status='Completed'
        )
        OrderItem.objects.create(order=order2, medicine=self.medicine, quantity=1, total_price=5000)
        # auto_now_add ignores values passed at creation time, so backdate via a queryset update
        last_year_date = now.replace(year=now.year - 1)
        Order.objects.filter(id=order2.id).update(created_at=last_year_date)

        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))

        self.assertEqual(response.context['best_year'], now.year - 1)

    def test_monthly_sales_series_length_is_twelve(self):
        give_active_subscription(self.seller, self.plan_with_analytics)
        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))

        import json
        month_labels = json.loads(response.context['month_labels'])
        sales_series = json.loads(response.context['sales_series'])
        self.assertEqual(len(month_labels), 12)
        self.assertEqual(len(sales_series), 12)

    def test_yearly_history_covers_five_years(self):
        give_active_subscription(self.seller, self.plan_with_analytics)
        self.client.force_login(self.seller)
        response = self.client.get(reverse('store_analytics'))
        self.assertEqual(len(response.context['yearly_history']), 5)