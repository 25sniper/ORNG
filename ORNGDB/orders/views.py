from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.template.loader import render_to_string
from .models import CartItem, Order, OrderItem, DraftBill
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

@login_required
@require_POST
def quick_bill_create(request):
    if request.user.role != 'delivery':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    store_name = request.POST.get('store_name', '').strip()
    if not store_name:
        store_name = '-'

    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Extract items
    items = []
    for key, value in request.POST.items():
        if key.startswith('qty_'):
            try:
                product_id = int(key.split('_')[1])
                qty = int(value)
                if qty > 0:
                    product = Product.objects.filter(id=product_id, available=True).first()
                    if product:
                        custom_price_str = request.POST.get(f'price_{product_id}')
                        if custom_price_str is not None and custom_price_str.strip() != '':
                            price = float(custom_price_str)
                        else:
                            price = float(product.price)
                        items.append((product, qty, price))
            except (ValueError, IndexError):
                continue
                
    if not items:
        return JsonResponse({'success': False, 'error': 'Please select at least one item.'})

    item_order_str = request.POST.get('item_order', '').strip()
    if item_order_str:
        try:
            ordered_ids = [int(x) for x in item_order_str.split(',') if x.strip()]
            items.sort(key=lambda x: ordered_ids.index(x[0].id) if x[0].id in ordered_ids else 999)
        except ValueError:
            pass

    old_balance = 0.00
    try:
        old_balance = float(request.POST.get('old_balance', 0) or 0)
        if old_balance < 0:
            old_balance = 0.00
    except (ValueError, TypeError):
        old_balance = 0.00

    try:
        with transaction.atomic():
            total_amount = sum(price * q for p, q, price in items)
            
            customer = User.objects.filter(role='customer', store_name__iexact=store_name).first()
            
            # If old_balance > 0, all previous unpaid orders for this store
            # are now settled — their balance is carried into this new bill.
            if old_balance > 0 and store_name != '-':
                from decimal import Decimal
                prior_unpaid = Order.objects.filter(
                    store_name__iexact=store_name,
                    payment_status='unpaid'
                ).exclude(status='cancelled')
                prior_unpaid.update(
                    payment_status='paid',
                    remaining_balance=Decimal('0.00')
                )
            
            status = 'received'
            target_tab = '#completed-tab'
                
            order = Order.objects.create(
                customer=customer,
                store_name=customer.store_name if customer else store_name,
                status=status,
                total_amount=total_amount,
                old_balance=old_balance,
                assigned_delivery_user=request.user,
                packed_at=timezone.now(),
                delivered_at=timezone.now()
            )
            if status == 'received':
                order.received_at = timezone.now()
                order.save()
                
            for product, qty, price in items:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price_at_time=price
                )
                
        msg = f"✓ Quick Bill #{order.id} placed successfully!"
        # Clear the draft bill for this delivery user
        DraftBill.objects.filter(delivery_user=request.user).delete()
        return JsonResponse({'success': True, 'message': msg, 'target_tab': target_tab})
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred while placing the bill.'})

@login_required
@require_POST
def toggle_order_payment_status(request, order_id):
    if request.user.role != 'delivery':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    order = get_object_or_404(Order, id=order_id)
    
    amount_paid_str = request.POST.get('amount_paid')
    if amount_paid_str is not None:
        from decimal import Decimal
        try:
            amount_paid = Decimal(amount_paid_str)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)
            
        # Use the current remaining balance as the base; fall back to grand total only if unset
        if order.remaining_balance is not None:
            current_due = order.remaining_balance
        else:
            current_due = order.total_amount + order.old_balance
            
        remaining = current_due - amount_paid
        if remaining < 0:
            remaining = Decimal('0.00')
            
        order.remaining_balance = remaining
        
        if remaining == Decimal('0.00'):
            order.payment_status = 'paid'
        else:
            order.payment_status = 'unpaid'
            
        order.save()
        
        return JsonResponse({
            'success': True, 
            'payment_status': order.payment_status,
            'remaining_balance': float(order.remaining_balance)
        })
        
    new_status = 'paid' if order.payment_status == 'unpaid' else 'unpaid'
    order.payment_status = new_status
    if new_status == 'paid':
        from decimal import Decimal
        order.remaining_balance = Decimal('0.00')
    else:
        order.remaining_balance = order.total_amount + order.old_balance
    order.save()
    
    return JsonResponse({
        'success': True, 
        'payment_status': new_status,
        'remaining_balance': float(order.remaining_balance)
    })

@login_required
@require_POST
def pay_store_balance(request):
    if request.user.role != 'delivery':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    store_name = request.POST.get('store_name')
    amount_paid_str = request.POST.get('amount_paid')
    
    if not store_name or amount_paid_str is None:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)
        
    from decimal import Decimal
    try:
        amount_paid = Decimal(amount_paid_str)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)
        
    if amount_paid <= 0:
        return JsonResponse({'success': False, 'error': 'Amount must be greater than zero'}, status=400)
        
    unpaid_orders = Order.objects.filter(
        store_name__iexact=store_name,
        payment_status='unpaid'
    ).exclude(
        status='cancelled'
    ).order_by('id')
    
    remaining_to_distribute = amount_paid
    
    for order in unpaid_orders:
        if remaining_to_distribute <= 0:
            break
            
        order_balance = order.remaining_balance
        if order_balance is None:
            order_balance = order.total_amount + order.old_balance
            
        if order_balance <= 0:
            continue
            
        if remaining_to_distribute >= order_balance:
            remaining_to_distribute -= order_balance
            order.remaining_balance = Decimal('0.00')
            order.payment_status = 'paid'
        else:
            order.remaining_balance = order_balance - remaining_to_distribute
            remaining_to_distribute = Decimal('0.00')
            order.payment_status = 'unpaid'
            
        order.save()
        
    return JsonResponse({
        'success': True,
        'message': f'Successfully paid ₹{amount_paid:.2f} towards store balance.'
    })

@login_required
def share_order_bill(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.user.role not in ['delivery', 'admin']:
        if order.customer != request.user:
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
            
    divider_double = "=" * 32
    divider_single = "-" * 32
    
    header = [
        divider_double,
        "ESTIMATION".center(32),
        divider_double
    ]
    
    local_dt = timezone.localtime(order.created_at)
    date_str = local_dt.strftime('%d/%m/%Y')
    time_str = local_dt.strftime('%H:%M')
    order_num = f"#{order.id:05d}"
    
    customer_name = order.display_customer_name
    
    details = [
        f"ORDER NO: {order_num}".ljust(32),
        f"DATE: {date_str} | TIME: {time_str}".ljust(32),
        " " * 32,
        "CUSTOMER DETAILS:".ljust(32),
        f"Name: {customer_name}".ljust(32),
        divider_single,
        "NO ITEM          QTY       TOTAL",
        divider_single
    ]
    
    items_lines = []
    import textwrap
    for idx, item in enumerate(order.items.all(), 1):
        desc = item.product.name
        wrapped_desc = textwrap.wrap(desc, width=14)
        if not wrapped_desc:
            wrapped_desc = [""]
            
        no_str = f"{idx}."
        no_str = no_str.ljust(3)[:3]
        
        qty_str = str(item.quantity).rjust(3)[:3]
        
        total_val = item.price_at_time * item.quantity
        total_str = f"{total_val:.2f}"
        if len(total_str) > 6:
            total_str = f"{total_val:.1f}"
        if len(total_str) > 6:
            total_str = f"{int(total_val)}"
        total_str = total_str.rjust(6)[:6]
        
        first_name_part = wrapped_desc[0].ljust(14)
        first_line = f"{no_str}{first_name_part}{qty_str}      {total_str}"
        items_lines.append(first_line)
        
        for line in wrapped_desc[1:]:
            items_lines.append("   " + line.ljust(14) + " " * 15)
        
    total_label = "TOTAL:"
    total_val_str = f"₹{order.total_amount:.2f}"
    spaces_needed = 32 - len(total_label) - len(total_val_str)
    if spaces_needed < 1:
        spaces_needed = 1
    total_line = f"{total_label}{' ' * spaces_needed}{total_val_str}"

    old_bal = order.old_balance
    grand = order.grand_total

    if old_bal > 0:
        old_bal_label = "OLD BALANCE:"
        old_bal_str = f"₹{old_bal:.2f}"
        sp = 32 - len(old_bal_label) - len(old_bal_str)
        old_bal_line = f"{old_bal_label}{' ' * max(1, sp)}{old_bal_str}"

        grand_label = "GRAND TOTAL:"
        grand_str = f"₹{grand:.2f}"
        sp2 = 32 - len(grand_label) - len(grand_str)
        grand_line = f"{grand_label}{' ' * max(1, sp2)}{grand_str}"

        totals_lines = [total_line, old_bal_line, grand_line]
    else:
        totals_lines = [total_line]

    payment_status_text = f"PAYMENT STATUS: {order.payment_status.upper()}"
    payment_line = payment_status_text.ljust(32)

    footer = [
        divider_single,
        *totals_lines,
        " " * 32,
        " " * 32,
        payment_line,
        " " * 32,
        "Thank you for your business!".center(32),
        divider_double
    ]
    
    bill_text = "\n".join(header + details + items_lines + [" " * 32, " " * 32] + footer)
    return JsonResponse({'success': True, 'bill_text': bill_text})


# ── Draft Bill Views ─────────────────────────────────────────────────────────
@login_required
def draft_bill_get(request):
    """Return current draft bill for the logged-in delivery user."""
    if request.user.role != 'delivery':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        draft = DraftBill.objects.get(delivery_user=request.user)
        return JsonResponse({
            'has_draft': True,
            'items': draft.items_json,
            'store_name': draft.store_name,
            'old_balance': str(draft.old_balance),
        })
    except DraftBill.DoesNotExist:
        return JsonResponse({'has_draft': False})


@login_required
@require_POST
def draft_bill_save(request):
    """Save or update the current draft bill for the logged-in delivery user."""
    if request.user.role != 'delivery':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    import json as _json
    try:
        data = _json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    items = data.get('items', {})
    store_name = data.get('store_name', '')
    old_balance = data.get('old_balance', 0)

    # Only save if there is at least one item
    has_items = any(int(v) > 0 for v in items.values() if str(v).isdigit() or isinstance(v, int))
    if not has_items:
        # Nothing to save — clear any existing draft
        DraftBill.objects.filter(delivery_user=request.user).delete()
        return JsonResponse({'saved': False, 'cleared': True})

    DraftBill.objects.update_or_create(
        delivery_user=request.user,
        defaults={
            'items_json': items,
            'store_name': store_name,
            'old_balance': old_balance,
        }
    )
    return JsonResponse({'saved': True})


@login_required
@require_POST
def draft_bill_clear(request):
    """Delete the current draft bill for the logged-in delivery user."""
    if request.user.role != 'delivery':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    DraftBill.objects.filter(delivery_user=request.user).delete()
    return JsonResponse({'cleared': True})

@login_required
def store_orders_api(request):
    if request.user.role != 'delivery':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    store_name = request.GET.get('store_name', '').strip()
    if not store_name:
        return JsonResponse({'error': 'Store name is required'}, status=400)
        
    orders = Order.objects.filter(store_name__iexact=store_name).order_by('-created_at')
    
    orders_data = []
    for order in orders:
        items = []
        for item in order.items.all().select_related('product'):
            items.append({
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': float(item.price_at_time),
                'total': float(item.row_total)
            })
            
        # Format dates nicely
        created_at_str = order.created_at.strftime('%b %d, %Y • %I:%M %p') if order.created_at else ''
        
        orders_data.append({
            'id': order.id,
            'created_at': created_at_str,
            'status': order.get_status_display(),
            'payment_status': order.payment_status,
            'total_amount': float(order.total_amount),
            'old_balance': float(order.old_balance),
            'grand_total': float(order.grand_total),
            'remaining_balance': float(order.remaining_balance) if order.remaining_balance is not None else float(order.grand_total),
            'items': items
        })
        
    return JsonResponse({
        'store_name': store_name,
        'orders': orders_data
    })
