import json
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
from store.models import Store
from django.db.models import Sum, Q

def home_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        elif request.user.role == 'agent':
            return redirect('delivery_dashboard')
        else:
            return redirect('login')
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
def customer_menu(request):
    if request.user.role != 'customer':
        return redirect('home')
        
    products = Product.objects.filter(available=True).order_by('position', 'name')
    cart_items = CartItem.objects.filter(customer=request.user)
    cart_count = cart_items.aggregate(total_qty=Sum('quantity'))['total_qty'] or 0
    
    cart_map = {item.product_id: item.quantity for item in cart_items}
    for product in products:
        product.cart_qty = cart_map.get(product.id, 0)
    
    context = {
        'products': products,
        'cart_count': cart_count,
    }
    return render(request, 'users/customer_menu.html', context)

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        return redirect('home')
        
    orders = Order.objects.all().select_related('customer', 'assigned_delivery_user').prefetch_related('items__product').order_by('-created_at')
    delivery_users = User.objects.filter(role='agent')
    
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
            role='agent'
        )
        messages.success(request, f'Agent account {username} created successfully.')
        
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
def pack_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'agent' and order.assigned_delivery_user == request.user:
        if order.status == 'pending':
            order.status = 'packed'
            order.packed_at = timezone.now()
            order.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'Order #{order.id} packed successfully.', 'new_status': 'packed'})
            messages.success(request, f'Order #{order.id} packed successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} is already {order.status}.'})
            messages.error(request, f'Order #{order.id} is already {order.status}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to pack this order.'}, status=403)
        messages.error(request, 'You do not have permission to pack this order.')

    return redirect('delivery_dashboard')

@login_required
@require_POST
def deliver_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'agent' and order.assigned_delivery_user == request.user:
        if order.status == 'packed':
            order.status = 'delivered'
            order.delivered_at = timezone.now()
            order.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'Order #{order.id} marked as delivered successfully.', 'new_status': 'delivered'})
            messages.success(request, f'Order #{order.id} marked as delivered successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} cannot be delivered as it is not packed.'})
            messages.error(request, f'Order #{order.id} cannot be delivered as it is not packed.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to deliver this order.'}, status=403)
        messages.error(request, 'You do not have permission to deliver this order.')

    return redirect('delivery_dashboard')

@login_required
@require_POST
def delivery_cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'agent' and order.assigned_delivery_user == request.user:
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

    if request.user.role == 'agent' and order.assigned_delivery_user == request.user:
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
    if request.user.role != 'agent':
        return redirect('home')
        
    all_orders = Order.objects.filter(
        assigned_delivery_user=request.user
    ).select_related('customer').prefetch_related('items__product').order_by('-created_at')
    
    # Hide the active draft edit order if there is one
    draft_edit_order_id = None
    try:
        draft = DraftBill.objects.get(delivery_user=request.user)
        draft_edit_order_id = draft.items_json.get('_edit_order_id')
    except DraftBill.DoesNotExist:
        pass
        
    if draft_edit_order_id:
        all_orders = all_orders.exclude(id=draft_edit_order_id)
        
    # Maintain compatibility with javascript/templates
    packing_orders = Order.objects.none()
    delivery_orders = Order.objects.none()
    completed_orders = all_orders

    from django.db.models import Sum, F, Max
    from django.db.models.functions import Lower, Coalesce

    # Get stores owned by this agent
    agent_stores = Store.objects.filter(owner=request.user).order_by('name')
    
    # Calculate unpaid balance for each store name
    unpaid_balances = Order.objects.filter(
        assigned_delivery_user=request.user,
        payment_status='unpaid'
    ).exclude(
        status='cancelled'
    ).annotate(
        store_name_lower=Lower('store_name')
    ).values('store_name_lower').annotate(
        balance=Sum(Coalesce('remaining_balance', F('total_amount') + F('old_balance')))
    )
    balance_map = {item['store_name_lower'].strip(): item['balance'] for item in unpaid_balances}
    
    stores_list = []
    for s in agent_stores:
        s_name_lower = s.name.lower().strip()
        balance = balance_map.get(s_name_lower, 0.00)
        stores_list.append({
            'id': s.id,
            'name': s.name,
            'owner_name': s.name,
            'phone': s.phone,
            'location': '',
            'google_maps_url': '',
            'balance': balance,
            'is_registered': True
        })
        
    has_draft = DraftBill.objects.filter(delivery_user=request.user).exists()
    
    # Find the latest order ID for each store to prevent modifying old orders
    latest_orders_qs = Order.objects.exclude(status='cancelled').annotate(
        store_name_lower=Lower('store_name')
    ).values('store_name_lower').annotate(max_id=Max('id'))
    latest_order_ids = [item['max_id'] for item in latest_orders_qs if item['max_id']]

    context = {
        'packing_orders': packing_orders,
        'delivery_orders': delivery_orders,
        'completed_orders': completed_orders,
        'products': Product.objects.filter(agent=request.user, available=True).order_by('position', 'name'),
        'existing_stores': Store.objects.filter(owner=request.user).values_list('name', flat=True).distinct().order_by('name'),
        'stores_list': stores_list,
        'has_draft': has_draft,
        'latest_order_ids': latest_order_ids,
    }
    return render(request, 'users/delivery_dashboard.html', context)
@login_required
def delivery_pack_order(request, order_id):
    if request.user.role != 'delivery':
        return redirect('home')
        
    order = get_object_or_404(Order, id=order_id)
    
    if request.user.role == 'delivery' and order.assigned_delivery_user != request.user:
        messages.error(request, 'You do not have permission to pack this order.')
        return redirect('delivery_dashboard')
        
    if order.status != 'pending':
        messages.error(request, f'Order #{order.id} is already {order.status}.')
        return redirect('delivery_dashboard')
        
    context = {
        'order': order,
    }
    return render(request, 'users/delivery_pack_order.html', context)

@login_required
@require_POST
def admin_add_product(request):
    if request.user.role != 'agent':
        return redirect('home')
        
    name = request.POST.get('name')
    price = request.POST.get('price')
    icon = request.POST.get('icon', '')
    image = request.FILES.get('image')
    
    if name and price:
        Product.objects.create(
            name=name,
            price=price,
            icon=icon,
            image=image,
            agent=request.user,
            available=True
        )
        messages.success(request, f'Product {name} added successfully.')
    else:
        messages.error(request, 'Please provide name and price.')
        
    return redirect('admin_products_view')

@login_required
@require_POST
def admin_edit_product(request, product_id):
    if request.user.role != 'agent':
        return redirect('home')
        
    product = get_object_or_404(Product, id=product_id, agent=request.user)
    
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
    if request.user.role != 'agent':
        return redirect('home')
    products = Product.objects.filter(agent=request.user).order_by('position', 'name')
    return render(request, 'users/admin_products.html', {'products': products})

@login_required
def admin_stores_view(request):
    if request.user.role != 'agent':
        return redirect('home')
        
    from django.db.models import Sum, F
    from django.db.models.functions import Lower, Coalesce
    
    stores = Store.objects.filter(owner=request.user).order_by('name')
    
    # Calculate unpaid balance for each store name for this agent
    unpaid_balances = Order.objects.filter(
        assigned_delivery_user=request.user,
        payment_status='unpaid'
    ).exclude(
        status='cancelled'
    ).annotate(
        store_name_lower=Lower('store_name')
    ).values('store_name_lower').annotate(
        balance=Sum(Coalesce('remaining_balance', F('total_amount') + F('old_balance')))
    )
    balance_map = {item['store_name_lower'].strip(): item['balance'] for item in unpaid_balances}
    
    # Attach balance to store objects
    for s in stores:
        s_name_lower = s.name.lower().strip()
        s.balance = balance_map.get(s_name_lower, 0.00)
        
    return render(request, 'users/admin_stores.html', {'stores': stores})

@login_required
@require_POST
def admin_add_store(request):
    if request.user.role != 'agent':
        return redirect('home')
    name = request.POST.get('name')
    phone = request.POST.get('phone', '')
    if name:
        Store.objects.create(owner=request.user, name=name, phone=phone)
        messages.success(request, f'Store "{name}" added successfully.')
    else:
        messages.error(request, 'Store name is required.')
    return redirect('admin_stores_view')

@login_required
@require_POST
def admin_edit_store(request, store_id):
    if request.user.role != 'agent':
        return redirect('home')
    store = get_object_or_404(Store, id=store_id, owner=request.user)
    name = request.POST.get('name')
    phone = request.POST.get('phone', '')
    if name:
        store.name = name
        store.phone = phone
        store.save()
        messages.success(request, f'Store "{name}" updated successfully.')
    else:
        messages.error(request, 'Store name is required.')
    return redirect('admin_stores_view')

@login_required
@require_POST
def admin_delete_store(request, store_id):
    if request.user.role != 'agent':
        return redirect('home')
    store = get_object_or_404(Store, id=store_id, owner=request.user)
    store.delete()
    messages.success(request, 'Store deleted successfully.')
    return redirect('admin_stores_view')

@login_required
def admin_staff_view(request):
    if request.user.role != 'admin':
        return redirect('home')
    delivery_users = User.objects.filter(role='agent')
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
                
        if role == 'agent':
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
