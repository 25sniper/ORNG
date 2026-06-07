from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.template.loader import render_to_string
from .models import CartItem, Order, OrderItem
from products.models import Product

@login_required
def cart_view(request):
    if request.user.role != 'customer':
        return redirect('home')
        
    cart_items = list(CartItem.objects.filter(customer=request.user).select_related('product'))
    total_amount = 0
    for item in cart_items:
        item.subtotal = item.product.price * item.quantity
        item.original_subtotal = (item.subtotal * 115) / 100
        total_amount += item.subtotal
    
    context = {
        'cart_items': cart_items,
        'total_amount': total_amount,
    }
    return render(request, 'orders/cart.html', context)

@login_required
@require_POST
def cart_add(request, product_id):
    if request.user.role != 'customer':
        return redirect('home')
        
    product = get_object_or_404(Product, id=product_id, available=True)
    try:
        quantity = int(round(float(request.POST.get('quantity', 1))))
    except (ValueError, TypeError):
        quantity = 1

    if quantity <= 0:
        messages.error(request, 'Quantity must be greater than zero.')
        return redirect('customer_menu')

    cart_item, created = CartItem.objects.get_or_create(
        customer=request.user,
        product=product,
        defaults={'quantity': quantity}
    )
    
    if not created:
        cart_item.quantity += quantity
        cart_item.save()
        
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        cart_count = sum(item.quantity for item in CartItem.objects.filter(customer=request.user))
        html = render_to_string('users/partials/qty_controls.html', {'product': product, 'cart_qty': cart_item.quantity}, request=request)
        return JsonResponse({'success': True, 'cart_count': cart_count, 'html': html})
        
    # If added from the cart page itself or redirecting, but normally we redirect to menu
    return redirect('customer_menu')

@login_required
@require_POST
def cart_update(request, item_id):
    if request.user.role != 'customer':
        return redirect('home')
        
    cart_item = get_object_or_404(CartItem, id=item_id, customer=request.user)
    action = request.POST.get('action')
    quantity_str = request.POST.get('quantity')

    if action == 'increase':
        cart_item.quantity += 1
        cart_item.save()
    elif action == 'decrease':
        cart_item.quantity -= 1
        if cart_item.quantity <= 0:
            cart_item.delete()
        else:
            cart_item.save()
    elif quantity_str is not None:
        try:
            quantity = int(round(float(quantity_str)))
        except (ValueError, TypeError):
            quantity = 1

        if quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()
        
    return redirect('cart_view')

@login_required
@require_POST
def cart_remove(request, item_id):
    if request.user.role != 'customer':
        return redirect('home')
        
    cart_item = get_object_or_404(CartItem, id=item_id, customer=request.user)
    cart_item.delete()
    return redirect('cart_view')

@login_required
@require_POST
def checkout(request):
    if request.user.role != 'customer':
        return redirect('home')
        
    cart_items = CartItem.objects.filter(customer=request.user).select_related('product')
    if not cart_items.exists():
        messages.error(request, 'Your cart is empty.')
        return redirect('customer_menu')
        
    try:
        with transaction.atomic():
            total_amount = sum(item.product.price * item.quantity for item in cart_items)
            
            order = Order.objects.create(
                customer=request.user,
                status='pending',
                total_amount=total_amount
            )
            
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price_at_time=item.product.price
                )
            
            # Clear cart
            cart_items.delete()
            
        messages.success(request, 'Order placed successfully!')
        return redirect('my_orders')
    except Exception as e:
        messages.error(request, 'An error occurred during checkout. Please try again.')
        return redirect('cart_view')

@login_required
def my_orders(request):
    if request.user.role != 'customer':
        return redirect('home')
        
    orders = Order.objects.filter(customer=request.user).order_by('-created_at').prefetch_related('items__product')
    return render(request, 'orders/my_orders.html', {'orders': orders})

@login_required
def order_detail(request, order_id):
    if request.user.role != 'customer':
        return redirect('home')
        
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'orders/order_detail.html', {'order': order})

@login_required
@require_POST
def mark_order_received(request, order_id):
    if request.user.role != 'customer':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        return redirect('home')

    order = get_object_or_404(Order, id=order_id, customer=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if order.status == 'delivered':
        order.status = 'received'
        order.received_at = timezone.now()
        order.save()
        if is_ajax:
            return JsonResponse({'success': True, 'message': f'Order #{order.id} marked as received. Thank you!'})
        messages.success(request, f'Order #{order.id} marked as received. Thank you!')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'This order cannot be marked as received yet.'})
        messages.error(request, 'This order cannot be marked as received yet.')

    return redirect('my_orders')

@login_required
@require_POST
def cancel_order(request, order_id):
    if request.user.role != 'customer':
        return redirect('home')
        
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    if order.status == 'pending':
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Order #{order.id} has been cancelled.')
    else:
        messages.error(request, 'This order cannot be cancelled as it is no longer pending.')
        
    return redirect('my_orders')

@login_required
@require_POST
def cart_update_qty(request, product_id):
    if request.user.role != 'customer':
        return redirect('home')
    product = get_object_or_404(Product, id=product_id)
    action = request.POST.get('action')
    
    cart_item, created = CartItem.objects.get_or_create(
        customer=request.user,
        product=product,
        defaults={'quantity': 0}
    )
    
    quantity_str = request.POST.get('quantity')
    
    if action == 'increase':
        cart_item.quantity += 1
        cart_item.save()
    elif action == 'decrease':
        cart_item.quantity -= 1
        if cart_item.quantity <= 0:
            cart_item.delete()
        else:
            cart_item.save()
    elif quantity_str is not None:
        try:
            val = int(round(float(quantity_str)))
        except (ValueError, TypeError):
            val = 0
            
        if val <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = val
            cart_item.save()
            
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        cart_count = sum(item.quantity for item in CartItem.objects.filter(customer=request.user))
        current_qty = cart_item.quantity if cart_item.id else 0
        html = render_to_string('users/partials/qty_controls.html', {'product': product, 'cart_qty': current_qty}, request=request)
        return JsonResponse({'success': True, 'cart_count': cart_count, 'html': html})
            
    return redirect('customer_menu')
