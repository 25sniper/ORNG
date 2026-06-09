from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from .models import User
from orders.models import Order, CartItem
from products.models import Product
from django.db.models import Sum

def home_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        elif request.user.role == 'delivery':
            return redirect('delivery_dashboard')
        else:
            return redirect('customer_menu')
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
        
    products = Product.objects.filter(available=True).order_by('name')
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
def pack_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.user.role == 'delivery' and order.assigned_delivery_user == request.user:
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

    if request.user.role == 'delivery' and order.assigned_delivery_user == request.user:
        if order.status == 'packed':
            order.status = 'delivered'
            order.delivered_at = timezone.now()
            order.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'Order #{order.id} marked as delivered successfully.', 'new_status': 'delivered'})
            messages.success(request, f'Order #{order.id} marked as delivered successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': f'Order #{order.id} is already {order.status}.'})
            messages.error(request, f'Order #{order.id} is already {order.status}.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'You do not have permission to deliver this order.'}, status=403)
        messages.error(request, 'You do not have permission to deliver this order.')

    return redirect('delivery_dashboard')

@login_required
def delivery_dashboard(request):
    if request.user.role != 'delivery':
        return redirect('home')
        
    packing_orders = Order.objects.filter(
        assigned_delivery_user=request.user,
        status='pending'
    ).select_related('customer').prefetch_related('items__product').order_by('created_at')
    
    delivery_orders = Order.objects.filter(
        assigned_delivery_user=request.user,
        status__in=['packed', 'delivered']
    ).select_related('customer').prefetch_related('items__product').order_by('created_at')
    
    completed_orders = Order.objects.filter(
        assigned_delivery_user=request.user,
        status='received'
    ).select_related('customer').prefetch_related('items__product').order_by('-received_at')
    
    context = {
        'packing_orders': packing_orders,
        'delivery_orders': delivery_orders,
        'completed_orders': completed_orders,
        'products': Product.objects.filter(available=True).order_by('name'),
        'existing_stores': User.objects.filter(role='customer').values_list('store_name', flat=True).distinct().order_by('store_name'),
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
    if request.user.role != 'admin':
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
            available=True
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
    products = Product.objects.all().order_by('name')
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
        username = request.POST.get('username')
        name = request.POST.get('name')
        store_name = request.POST.get('store_name')
        location = request.POST.get('location')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        
        if username and username != user.username:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('profile_view')
            user.username = username
            if user.role == 'customer':
                user.phone = username
                
        if user.role == 'delivery' and phone:
            if User.objects.filter(phone=phone).exclude(id=user.id).exists():
                messages.error(request, 'Mobile number already in use by another account.')
                return redirect('profile_view')
            user.phone = phone
                
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
