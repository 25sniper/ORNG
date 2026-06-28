import json
import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from .models import User
from orders.models import Order, CartItem, DraftBill
from products.models import Product
from django.db.models import Sum, Q, Max, F
from django.db.models.functions import Coalesce

def home_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        elif request.user.role == 'delivery':
            return redirect('delivery_dashboard')
        else:
            return redirect('customer_dashboard')
    return redirect('login')

def unified_login(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username_or_phone = request.POST.get('username_or_phone')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username_or_phone, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            if (username_or_phone.isdigit() and len(username_or_phone) == 10
                    and password == username_or_phone
                    and not User.objects.filter(phone=username_or_phone).exists()
                    and not User.objects.filter(username=username_or_phone).exists()):
                request.session['pending_registration_phone'] = username_or_phone
                request.session['pending_registration_password'] = password
                return redirect('register')
            
            messages.error(request, 'Invalid credentials.')
            
    return render(request, 'users/login.html')

def customer_register(request):
    phone = request.session.get('pending_registration_phone')
    password = request.session.get('pending_registration_password')
    
    if not phone or not password:
        return redirect('login')
        
    if request.method == 'POST':
        name = request.POST.get('name')
        store_name = request.POST.get('store_name')
        location = request.POST.get('location', '')
        google_maps_url = ''
        if location:
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={location.replace(' ', '+')}"
        
        user = User.objects.create_user(
            username=phone,
            password=password,
            phone=phone,
            role='customer',
            name=name,
            store_name=store_name,
            location=location,
            google_maps_url=google_maps_url
        )
        
        del request.session['pending_registration_phone']
        del request.session['pending_registration_password']
        
        login(request, user, backend='users.backends.CustomAuthBackend')
        return redirect('customer_menu')
        
    return render(request, 'users/register.html', {'phone': phone})

def user_logout(request):
    logout(request)
    return redirect('login')

@login_required
def customer_dashboard(request):
    if request.user.role != 'customer':
        return redirect('home')

    from orders.models import DraftBill
    has_draft = DraftBill.objects.filter(delivery_user=request.user).exists()

    products = Product.objects.filter(available=True).order_by('position', 'name')

    orders = Order.objects.filter(
        customer=request.user
    ).prefetch_related('items__product').order_by('-created_at')

    # Calculate unpaid balance for the logged-in customer
    balance = Order.objects.filter(
        payment_status='unpaid',
        customer=request.user
    ).exclude(status='cancelled').aggregate(
        balance=Sum(Coalesce('remaining_balance', F('total_amount') + F('old_balance')))
    )['balance'] or 0.00

    context = {
        'products': products,
        'orders': orders,
        'balance': balance,
        'has_draft': has_draft,
    }
    return render(request, 'users/customer_dashboard.html', context)






@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        return redirect('home')
        
    orders = Order.objects.all().select_related('customer', 'assigned_delivery_user').prefetch_related('items__product').order_by('-created_at')
    delivery_users = User.objects.filter(role='delivery')
    
    context = {
        'orders': orders,
        'delivery_users': delivery_users,
    }
    return render(request, 'users/admin_dashboard.html', context)

@login_required
@require_POST
def admin_assign_delivery(request, order_id):
    if request.user.role != 'admin':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        return redirect('home')
        
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if order.status in ['delivered', 'received', 'cancelled'] or (order.status == 'packed' and order.assigned_delivery_user):
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Assignment is frozen for this order.'})
        messages.error(request, 'Assignment is frozen for this order.')
        return redirect('admin_dashboard')
        
    delivery_user_id = request.POST.get('delivery_user_id')
    
    if delivery_user_id:
        delivery_user = get_object_or_404(User, id=delivery_user_id)
        order.assigned_delivery_user = delivery_user
        order.save()
        if is_ajax:
            return JsonResponse({'success': True, 'message': f'Order #{order.id} assigned to {delivery_user.name or delivery_user.username}.', 'assigned_name': delivery_user.name or delivery_user.username})
        messages.success(request, f'Order #{order.id} assigned to {delivery_user.name or delivery_user.username}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Please select a valid delivery person.'})
        messages.error(request, 'Please select a valid delivery person.')
        
    return redirect('admin_dashboard')

@login_required
@require_POST
def admin_create_delivery_account(request):
    if request.user.role != 'admin':
        return redirect('home')
        
    username = request.POST.get('username')
    password = request.POST.get('password')
    name = request.POST.get('name')
    phone = request.POST.get('phone')
    
    if User.objects.filter(username=username).exists():
        messages.error(request, f'Username {username} already exists.')
    elif phone and User.objects.filter(phone=phone).exists():
        messages.error(request, f'Mobile number {phone} is already in use.')
    else:
        User.objects.create_user(
            username=username,
            password=password,
            name=name,
            phone=phone,
            role='delivery'
        )
        messages.success(request, f'Delivery account {username} created successfully.')
        
    return redirect('admin_staff_view')

@login_required
@require_POST
def admin_toggle_product(request, product_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    product = get_object_or_404(Product, id=product_id)
    product.available = not product.available
    product.save()
    
    return JsonResponse({'available': product.available, 'name': product.name})

@login_required
@require_POST
def receive_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'delivery' and order.assigned_delivery_user == request.user:
        if order.status == 'pending':
            order.status = 'received'
            order.received_at = timezone.now()
            order.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'Order #{order.id} marked as completed successfully.', 'new_status': 'completed'})
            messages.success(request, f'Order #{order.id} marked as completed successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} is already {order.status}.'})
            messages.error(request, f'Order #{order.id} is already {order.status}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to complete this order.'}, status=403)
        messages.error(request, 'You do not have permission to complete this order.')

    return redirect('delivery_dashboard')

@login_required
@require_POST
def delivery_cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'delivery' and order.assigned_delivery_user == request.user:
        if order.status in ['pending', 'packed', 'delivered', 'received']:
            order.status = 'cancelled'
            order.save()
            
            # If this order is currently in the user's edit draft, delete the draft
            try:
                draft = DraftBill.objects.get(delivery_user=request.user)
                if draft.items_json and draft.items_json.get('_edit_order_id') == order.id:
                    draft.delete()
            except DraftBill.DoesNotExist:
                pass
            
            if order.old_balance > 0 and order.store_name:
                previous_order = Order.objects.filter(
                    store_name__iexact=order.store_name,
                    created_at__lt=order.created_at
                ).exclude(status='cancelled').order_by('-created_at').first()
                
                if previous_order:
                    previous_order.payment_status = 'unpaid'
                    previous_order.remaining_balance = order.old_balance
                    previous_order.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'Order #{order.id} cancelled successfully.', 'new_status': 'cancelled'})
            messages.success(request, f'Order #{order.id} cancelled successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} cannot be cancelled as it is {order.status}.'})
            messages.error(request, f'Order #{order.id} cannot be cancelled as it is {order.status}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to cancel this order.'}, status=403)
        messages.error(request, 'You do not have permission to cancel this order.')

    return redirect('delivery_dashboard')


@login_required
@require_POST
def delivery_edit_order_to_draft(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'delivery' and order.assigned_delivery_user == request.user:
        if order.status in ['pending', 'packed', 'delivered', 'received']:
            # 1. Revert previous orders' balances and payments (just like cancellation)
            if order.old_balance > 0 and order.store_name:
                previous_order = Order.objects.filter(
                    store_name__iexact=order.store_name,
                    created_at__lt=order.created_at
                ).exclude(status='cancelled').order_by('-created_at').first()
                
                if previous_order:
                    previous_order.payment_status = 'unpaid'
                    previous_order.remaining_balance = order.old_balance
                    previous_order.save()

            # 2. Extract items and populate DraftBill
            items_dict = {str(item.product_id): item.quantity for item in order.items.all()}
            items_dict['_edit_order_id'] = order.id
            
            custom_prices = {}
            for item in order.items.all():
                custom_prices[str(item.product_id)] = float(item.price_at_time)
            if custom_prices:
                items_dict['_custom_prices'] = custom_prices
                
            DraftBill.objects.update_or_create(
                delivery_user=request.user,
                defaults={
                    'items_json': items_dict,
                    'store_name': order.store_name,
                    'old_balance': order.old_balance,
                }
            )

            # 3. Temporarily mark the order as cancelled (will be restored to received when submitted)
            order.status = 'cancelled'
            order.save()

            if is_ajax:
                return JsonResponse({'success': True, 'message': 'Order loaded into edit draft successfully.'})
            messages.success(request, 'Order loaded into edit draft successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} cannot be edited as it is {order.status}.'})
            messages.error(request, f'Order #{order.id} cannot be edited as it is {order.status}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to edit this order.'}, status=403)
        messages.error(request, 'You do not have permission to edit this order.')

    return redirect('delivery_dashboard')


@login_required
def delivery_dashboard(request):
    if request.user.role != 'delivery':
        return redirect('home')
        
    pending_orders = Order.objects.filter(
        Q(status='pending') | Q(status='cancelled', received_at__isnull=True),
        assigned_delivery_user=request.user
    ).select_related('customer').prefetch_related('items__product').order_by('-created_at')
    
    received_orders = Order.objects.filter(
        Q(status='received') | Q(status='cancelled', received_at__isnull=False),
        assigned_delivery_user=request.user
    ).select_related('customer').prefetch_related('items__product').order_by('-received_at')
    
    from django.db.models import Sum, F, Max
    from django.db.models.functions import Lower, Coalesce

    customers = User.objects.filter(role='customer').order_by('store_name')
    
    unpaid_balances = Order.objects.filter(
        payment_status='unpaid'
    ).exclude(
        status='cancelled'
    ).annotate(
        store_name_lower=Lower('store_name')
    ).values('store_name_lower').annotate(
        balance=Sum(Coalesce('remaining_balance', F('total_amount') + F('old_balance')))
    )
    balance_map = {item['store_name_lower']: item['balance'] for item in unpaid_balances}
    
    stores_list = []
    registered_store_names_lower = set()
    
    for c in customers:
        store_name_lower = c.store_name.lower().strip()
        registered_store_names_lower.add(store_name_lower)
        balance = balance_map.get(store_name_lower, 0.00)
        stores_list.append({
            'id': c.id,
            'name': c.store_name or c.name or c.username,
            'owner_name': c.name,
            'phone': c.phone,
            'location': c.location,
            'google_maps_url': c.google_maps_url,
            'balance': balance,
            'is_registered': True
        })
        
    for item in unpaid_balances:
        s_name_lower = item['store_name_lower']
        if s_name_lower not in registered_store_names_lower and s_name_lower.strip() and s_name_lower != '-':
            orig_order = Order.objects.filter(store_name__iexact=s_name_lower).first()
            orig_name = orig_order.store_name if orig_order else s_name_lower
            stores_list.append({
                'id': None,
                'name': orig_name,
                'owner_name': 'Guest Customer',
                'phone': orig_order.customer.phone if (orig_order and orig_order.customer) else None,
                'location': orig_order.customer.location if (orig_order and orig_order.customer) else None,
                'google_maps_url': orig_order.customer.google_maps_url if (orig_order and orig_order.customer) else None,
                'balance': item['balance'],
                'is_registered': False
            })
            
    stores_list = sorted(stores_list, key=lambda x: x['name'].lower())

    has_draft = DraftBill.objects.filter(delivery_user=request.user).exists()
    
    # Find the latest order ID for each store to prevent modifying old orders
    latest_orders_qs = Order.objects.exclude(status='cancelled').annotate(
        store_name_lower=Lower('store_name')
    ).values('store_name_lower').annotate(latest_id=Max('id'))
    
    latest_order_ids = [item['latest_id'] for item in latest_orders_qs]

    draft_edit_order_id = None
    if has_draft:
        try:
            draft = DraftBill.objects.get(delivery_user=request.user)
            draft_edit_order_id = draft.items_json.get('_edit_order_id', None) if isinstance(draft.items_json, dict) else None
        except DraftBill.DoesNotExist:
            pass
        
    if draft_edit_order_id:
        pending_orders = pending_orders.exclude(id=draft_edit_order_id)
        received_orders = received_orders.exclude(id=draft_edit_order_id)

    context = {
        'pending_orders': pending_orders,
        'received_orders': received_orders,
        'delivery_orders': list(pending_orders) + list(received_orders),
        'products': Product.objects.filter(available=True).order_by('position', 'name'),
        'existing_stores': User.objects.filter(role='customer').values_list('store_name', flat=True).distinct().order_by('store_name'),
        'stores_list': stores_list,
        'has_draft': has_draft,
        'latest_order_ids': latest_order_ids,
    }
    return render(request, 'users/delivery_dashboard.html', context)

@login_required
@require_POST
def admin_add_product(request):
    if request.user.role != 'admin':
        return redirect('home')
        
    name = request.POST.get('name')
    price = request.POST.get('price')
    icon = request.POST.get('icon', '')
    image = request.FILES.get('image')
    
    if name and price:
        max_pos = Product.objects.aggregate(Max('position'))['position__max']
        next_pos = (max_pos + 1) if max_pos is not None else 0
        Product.objects.create(
            name=name,
            price=price,
            icon=icon,
            image=image,
            available=True,
            position=next_pos
        )
        messages.success(request, f'Product {name} added successfully.')
    else:
        messages.error(request, 'Please provide name and price.')
        
    return redirect('admin_products_view')

@login_required
@require_POST
def admin_edit_product(request, product_id):
    if request.user.role != 'admin':
        return redirect('home')
        
    product = get_object_or_404(Product, id=product_id)
    
    name = request.POST.get('name')
    price = request.POST.get('price')
    icon = request.POST.get('icon', '')
    image = request.FILES.get('image')
    
    if name and price:
        product.name = name
        product.price = price
        product.icon = icon
        if image:
            product.image = image
        product.save()
        messages.success(request, f'Product {name} updated successfully.')
    else:
        messages.error(request, 'Please provide name and price.')
        
    return redirect('admin_products_view')

@login_required
def admin_products_view(request):
    if request.user.role != 'admin':
        return redirect('home')
    products = Product.objects.all().order_by('position', 'name')
    return render(request, 'users/admin_products.html', {'products': products})

@login_required
def admin_stores_view(request):
    if request.user.role != 'admin':
        return redirect('home')
    customers = User.objects.filter(role='customer')
    return render(request, 'users/admin_stores.html', {'customers': customers})

@login_required
def admin_staff_view(request):
    if request.user.role != 'admin':
        return redirect('home')
    delivery_users = User.objects.filter(role='delivery')
    return render(request, 'users/admin_staff.html', {'delivery_users': delivery_users})

@login_required
def admin_order_detail_view(request, order_id):
    if request.user.role != 'admin':
        return redirect('home')
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'users/admin_order_detail.html', {'order': order})

@login_required
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        role = user.role
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and username != user.username:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('profile_view')
            user.username = username
            if role == 'customer':
                user.phone = username
                
        if role == 'delivery':
            name = request.POST.get('name')
            phone = request.POST.get('phone')
            if phone:
                if User.objects.filter(phone=phone).exclude(id=user.id).exists():
                    messages.error(request, 'Mobile number already in use by another account.')
                    return redirect('profile_view')
                user.phone = phone
            if name is not None:
                user.name = name
                
        elif role == 'customer':
            name = request.POST.get('name')
            store_name = request.POST.get('store_name')
            location = request.POST.get('location')
            
            if name is not None:
                user.name = name
            if store_name is not None:
                user.store_name = store_name
            if location is not None and location != user.location:
                user.location = location
                if location:
                    user.google_maps_url = f"https://www.google.com/maps/search/?api=1&query={location.replace(' ', '+')}"
                else:
                    user.google_maps_url = ''
                    
        if password:
            user.set_password(password)
            
        user.save()
        
        if password:
            update_session_auth_hash(request, user)
            
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile_view')
        
    return render(request, 'users/profile.html')

@login_required
@require_POST
def admin_delete_order_history(request):
    if request.user.role != 'admin':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        return redirect('home')
        
    Order.objects.all().delete()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'All orders and balance history have been deleted successfully.'})
        
    messages.success(request, 'All orders and balance history have been deleted successfully.')
    return redirect('admin_dashboard')

@login_required
@require_POST
def admin_reorder_products(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        product_ids = data.get('order', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid data'}, status=400)

    if not product_ids:
        return JsonResponse({'error': 'No product IDs provided'}, status=400)

    for position, product_id in enumerate(product_ids):
        Product.objects.filter(id=product_id).update(position=position)

    return JsonResponse({'success': True})

@login_required
@require_POST
def admin_bulk_import_products(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    
    file = request.FILES['file']
    if not file.name.endswith('.csv'):
        return JsonResponse({'error': 'Please upload a valid CSV file'}, status=400)

    try:
        decoded_file = file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        
        for row in reader:
            name = row.get('name', '').strip()
            if not name:
                continue
            
            price = row.get('price', '0.00').strip()
            stock_quantity = row.get('stock_quantity', '').strip()
            available = row.get('available', 'True').strip().lower() in ['true', '1', 'yes']
            
            # Use defaults for update_or_create
            defaults = {
                'price': price if price else '0.00',
                'stock_quantity': stock_quantity if stock_quantity else None,
                'available': available
            }
            Product.objects.update_or_create(name=name, defaults=defaults)
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': f'Failed to process file: {str(e)}'}, status=500)


@login_required
def admin_bulk_export_preview(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    products = Product.objects.all().order_by('position', 'name')[:5]
    data = []
    for p in products:
        data.append({
            'name': p.name,
            'price': str(p.price),
            'stock_quantity': p.stock_quantity if p.stock_quantity is not None else '',
            'available': p.available
        })
    return JsonResponse({'products': data})


@login_required
def admin_bulk_export_products(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['name', 'price', 'stock_quantity', 'available'])
    
    products = Product.objects.all().order_by('position', 'name')
    for p in products:
        writer.writerow([
            p.name,
            p.price,
            p.stock_quantity if p.stock_quantity is not None else '',
            p.available
        ])
        
    return response


@login_required
@require_POST
def admin_bulk_delete_products(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    try:
        Product.objects.all().delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
