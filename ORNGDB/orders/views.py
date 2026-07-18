from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.conf import settings
from .models import CartItem, Order, OrderItem, DraftBill
from products.models import Product
from decimal import Decimal
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import time



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
def quick_bill_create(request):
    start_time = time.time()
    
    if request.user.role != 'delivery':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    store_name = request.POST.get('store_name', '').strip()
    if not store_name or store_name == '-':
        return JsonResponse({'success': False, 'error': 'Store selection is compulsory.'})

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
                            price = Decimal(str(custom_price_str))
                        else:
                            price = Decimal(str(product.price))
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

    old_balance = Decimal('0.00')
    try:
        old_balance = Decimal(str(request.POST.get('old_balance', 0) or 0))
        if old_balance < Decimal('0.00'):
            old_balance = Decimal('0.00')
    except (ValueError, TypeError, ArithmeticError):
        old_balance = Decimal('0.00')

    try:
        with transaction.atomic():
            total_amount = sum(price * q for p, q, price in items)
            
            customer = User.objects.filter(role='customer', store_name__iexact=store_name).first()
            
            edit_order_id = request.POST.get('order_id')
            
            if edit_order_id:
                order = get_object_or_404(Order, id=edit_order_id)
                
                # Get the original grand total and amount paid before updating
                orig_total = order.total_amount
                orig_old_balance = order.old_balance
                orig_grand_total = orig_total + orig_old_balance
                if order.remaining_balance is not None:
                    amount_paid_previously = orig_grand_total - order.remaining_balance
                else:
                    amount_paid_previously = Decimal('0.00')
                
                order.customer = customer
                order.store_name = customer.store_name if customer else store_name
                order.total_amount = total_amount
                order.old_balance = old_balance
                
                # Recalculate remaining balance
                grand_total = total_amount + old_balance
                new_remaining_balance = Decimal(str(grand_total)) - amount_paid_previously
                if new_remaining_balance < Decimal('0.00'):
                    new_remaining_balance = Decimal('0.00')
                    
                order.remaining_balance = new_remaining_balance
                if new_remaining_balance == Decimal('0.00'):
                    order.payment_status = 'paid'
                else:
                    order.payment_status = 'unpaid'
                order.status = 'received'
                order.received_at = timezone.now()
                order.save()
                
                # Remove existing items and recreate
                order.items.all().delete()
                for product, qty, price in items:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        price_at_time=price
                    )
                
                # If old_balance > 0, all previous unpaid orders for this store
                # are now settled — their balance is carried into this edited bill.
                if old_balance > 0 and store_name != '-':
                    prior_unpaid = Order.objects.filter(
                        store_name__iexact=store_name,
                        payment_status='unpaid'
                    ).exclude(status='cancelled').exclude(id=order.id)
                    prior_unpaid.update(
                        payment_status='paid',
                        remaining_balance=Decimal('0.00')
                    )
                
                msg = f"✓ Order #{order.id} updated successfully!"
                target_tab = None
                
            else:
                # If old_balance > 0, all previous unpaid orders for this store
                # are now settled — their balance is carried into this new bill.
                if old_balance > 0 and store_name != '-':
                    prior_unpaid = Order.objects.filter(
                        store_name__iexact=store_name,
                        payment_status='unpaid'
                    ).exclude(status='cancelled')
                    prior_unpaid.update(
                        payment_status='paid',
                        remaining_balance=Decimal('0.00')
                    )
                
                status = 'received'
                target_tab = '#received-tab'
                    
                order = Order.objects.create(
                    customer=customer,
                    store_name=customer.store_name if customer else store_name,
                    status=status,
                    total_amount=total_amount,
                    old_balance=old_balance,
                    original_old_balance=old_balance,
                    assigned_delivery_user=request.user,
                    received_at=timezone.now(),
                    processing_time_ms=int((time.time() - start_time) * 1000)
                )
                    
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
        
        # Determine target tab only for new creations
        return JsonResponse({
            'success': True, 
            'message': msg, 
            'target_tab': target_tab if not edit_order_id else None
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': 'An error occurred while placing the bill.'})

@login_required
@require_POST
def toggle_order_payment_status(request, order_id):
    if request.user.role != 'delivery':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    order = get_object_or_404(Order, id=order_id)
    
    amount_paid_str = request.POST.get('amount_paid')
    pay_pending_only = request.POST.get('pay_pending_only') == 'true'
    pay_old_balance_only = request.POST.get('pay_old_balance_only') == 'true'
    
    if pay_old_balance_only:
        paid_amt = order.old_balance
        order.old_balance = Decimal('0.00')
        if order.remaining_balance is not None:
            order.remaining_balance = max(Decimal('0.00'), order.remaining_balance - paid_amt)
        else:
            order.remaining_balance = order.total_amount
            
        if order.remaining_balance == Decimal('0.00'):
            order.payment_status = 'paid'
        else:
            order.payment_status = 'unpaid'
        order.save()
        return JsonResponse({
            'success': True, 
            'payment_status': order.payment_status,
            'remaining_balance': float(order.remaining_balance)
        })
        
    if pay_pending_only:
        order.old_balance = Decimal('0.00')
        order.remaining_balance = Decimal('0.00')
        order.payment_status = 'paid'
        order.save()
        return JsonResponse({
            'success': True, 
            'payment_status': order.payment_status,
            'remaining_balance': float(order.remaining_balance)
        })
        
    if amount_paid_str is not None:
        try:
            amount_paid = Decimal(amount_paid_str)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)
            

        # Use the current remaining balance as the base; fall back to grand total only if unset
        if order.remaining_balance is not None:
            current_due = order.remaining_balance
        else:
            current_due = order.total_amount + order.old_balance
            
        # Deduct old balance first
        old_bal_payment = min(amount_paid, order.old_balance)
        order.old_balance -= old_bal_payment
        
        # Synchronize previous unpaid orders
        if old_bal_payment > 0 and order.store_name:
            prior_unpaid = Order.objects.filter(
                store_name__iexact=order.store_name,
                payment_status='unpaid',
                created_at__lt=order.created_at
            ).exclude(status='cancelled').order_by('id')
            
            rem_to_dist = old_bal_payment
            for prior_order in prior_unpaid:
                if rem_to_dist <= 0:
                    break
                prior_bal = prior_order.remaining_balance
                if prior_bal is None:
                    prior_bal = prior_order.total_amount + prior_order.old_balance
                if prior_bal <= 0:
                    continue
                if rem_to_dist >= prior_bal:
                    rem_to_dist -= prior_bal
                    prior_order.remaining_balance = Decimal('0.00')
                    prior_order.payment_status = 'paid'
                else:
                    prior_order.remaining_balance = prior_bal - rem_to_dist
                    rem_to_dist = Decimal('0.00')
                    prior_order.payment_status = 'unpaid'
                prior_order.save()
        
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
        order.remaining_balance = Decimal('0.00')
        # Mark all prior unpaid orders as paid
        if order.old_balance > 0 and order.store_name:
            prior_unpaid = Order.objects.filter(
                store_name__iexact=order.store_name,
                payment_status='unpaid',
                created_at__lt=order.created_at
            ).exclude(status='cancelled')
            prior_unpaid.update(
                payment_status='paid',
                remaining_balance=Decimal('0.00')
            )
        order.old_balance = Decimal('0.00')
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
    orders_to_update = []
    
    for order in unpaid_orders:
        if remaining_to_distribute <= 0:
            break
            
        order_balance = order.remaining_balance
        if order_balance is None:
            order_balance = order.total_amount + order.old_balance
            
        if order_balance <= 0:
            continue
            
        if remaining_to_distribute >= order_balance:
            paid_amount_on_order = order_balance
            remaining_to_distribute -= order_balance
            order.remaining_balance = Decimal('0.00')
            order.payment_status = 'paid'
        else:
            paid_amount_on_order = remaining_to_distribute
            order.remaining_balance = order_balance - remaining_to_distribute
            remaining_to_distribute = Decimal('0.00')
            order.payment_status = 'unpaid'
            
        old_bal_payment = min(paid_amount_on_order, order.old_balance)
        order.old_balance -= old_bal_payment
            
        orders_to_update.append(order)
        
    if orders_to_update:
        Order.objects.bulk_update(orders_to_update, ['remaining_balance', 'payment_status', 'old_balance'])
        
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
            
    try:
        w = int(request.GET.get('width', 32))
    except ValueError:
        w = 32
        
    divider_double = "=" * w
    divider_single = "-" * w
    
    header = [
        divider_double,
        "ESTIMATION".center(w),
        divider_double
    ]
    
    local_dt = timezone.localtime(order.created_at)
    date_str = local_dt.strftime('%d/%m/%Y')
    time_str = local_dt.strftime('%H:%M')
    order_num = f"#{order.id:05d}"
    
    store_name = order.display_store_name
    
    # Calculate space for item name based on total width (32 - 18 = 14) -> (w - 18)
    name_w = max(10, w - 18)
    
    details = [
        f"ORDER NO: {order_num}".ljust(w),
        f"DATE: {date_str} | TIME: {time_str}".ljust(w),
        f"Store: {store_name}".ljust(w),
        divider_single,
        "NO ITEM".ljust(3 + name_w) + "QTY       TOTAL",
        divider_single
    ]
    
    items_lines = []
    import textwrap
    for idx, item in enumerate(order.items.all(), 1):
        desc = item.product.name
        wrapped_desc = textwrap.wrap(desc, width=name_w)
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
        
        first_name_part = wrapped_desc[0].ljust(name_w)
        first_line = f"{no_str}{first_name_part}{qty_str}      {total_str}"
        items_lines.append(first_line)
        
        for line in wrapped_desc[1:]:
            items_lines.append("   " + line.ljust(name_w) + " " * 15)
        
    total_label = "TOTAL:"
    total_val_str = f"₹{order.total_amount:.2f}"
    spaces_needed = w - len(total_label) - len(total_val_str)
    if spaces_needed < 1:
        spaces_needed = 1
    total_line = f"{total_label}{' ' * spaces_needed}{total_val_str}"

    old_bal = order.old_balance
    remaining = order.remaining_balance if order.remaining_balance is not None else order.grand_total

    totals_lines = [total_line]
    bill_type = getattr(request.user, 'bill_type', 'type1')

    if bill_type == 'type2':
        # Detailed Bill
        original_old = order.original_old_balance if order.original_old_balance is not None else old_bal
        grand_total = order.total_amount + original_old
        
        if original_old > 0:
            old_bal_label = "OLD BALANCE:"
            old_bal_str = f"₹{original_old:.2f}"
            sp = w - len(old_bal_label) - len(old_bal_str)
            totals_lines.append(f"{old_bal_label}{' ' * max(1, sp)}{old_bal_str}")
            
            grand_label = "GRAND TOTAL:"
            grand_str = f"₹{grand_total:.2f}"
            sp_grand = w - len(grand_label) - len(grand_str)
            totals_lines.append(f"{grand_label}{' ' * max(1, sp_grand)}{grand_str}")
            
        cash_paid = grand_total - remaining
        
        cash_label = "CASH:"
        cash_str = f"-₹{cash_paid:.2f}"
        sp_cash = w - len(cash_label) - len(cash_str)
        totals_lines.append(f"{cash_label}{' ' * max(1, sp_cash)}{cash_str}")
            
    else:
        # Compact Bill (Type 1)
        if old_bal > 0:
            old_bal_label = "OLD BALANCE:"
            old_bal_str = f"₹{old_bal:.2f}"
            sp = w - len(old_bal_label) - len(old_bal_str)
            totals_lines.append(f"{old_bal_label}{' ' * max(1, sp)}{old_bal_str}")
            
        product_remaining = max(Decimal('0.00'), remaining - old_bal)
        product_payment = order.total_amount - product_remaining
        
        # User requirement: dont show cash with old balance but show cash when there is only item total remaining to pay
        if old_bal == Decimal('0.00') and product_payment > 0:
            cash_label = "CASH:"
            cash_str = f"-₹{product_payment:.2f}"
            sp_cash = w - len(cash_label) - len(cash_str)
            totals_lines.append(f"{cash_label}{' ' * max(1, sp_cash)}{cash_str}")

    due_label = "NEW BALANCE:"
    due_str = f"₹{remaining:.2f}"
    sp_due = w - len(due_label) - len(due_str)
    due_line = f"{due_label}{' ' * max(1, sp_due)}{due_str}"
    totals_lines.append(due_line)

    payment_status_text = f"PAYMENT STATUS: {order.payment_status.upper()}"
    payment_line = payment_status_text.ljust(w)

    footer = [
        divider_single,
        *totals_lines,
        " " * w,
        " " * w,
        payment_line,
        " " * w,
        "Thank you for your business!".center(w),
        divider_double
    ]
    
    bill_text = "\n".join(header + details + items_lines + [" " * w, " " * w] + footer)
    
    format_type = request.GET.get('format', 'json')
    if format_type == 'image':
        font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'RobotoMono-Regular.ttf')
        try:
            font = ImageFont.truetype(font_path, 28)
        except IOError:
            font = ImageFont.load_default()

        lines = bill_text.split('\n')
        
        # Calculate dimensions
        max_width = 0
        total_height = 0
        line_heights = []
        
        # dummy image just for measuring
        dummy_img = Image.new('RGB', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        
        for line in lines:
            # textbbox returns (left, top, right, bottom)
            bbox = dummy_draw.textbbox((0, 0), line, font=font)
            w_line = bbox[2] - bbox[0]
            h_line = bbox[3] - bbox[1] + 10 # 10px spacing
            if h_line < 20: h_line = 38 # Fallback minimum line height for 28px font
            max_width = max(max_width, w_line)
            total_height += h_line
            line_heights.append(h_line)
            
        img_width = max_width + 40
        img_height = total_height + 40
        
        img = Image.new('RGB', (img_width, img_height), color='white')
        draw = ImageDraw.Draw(img)
        
        y_text = 20
        for i, line in enumerate(lines):
            draw.text((20, y_text), line, font=font, fill='black')
            y_text += line_heights[i]
            
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='image/png')

    return JsonResponse({'success': True, 'bill_text': bill_text})


# ── Draft Bill Views ─────────────────────────────────────────────────────────
@login_required
def draft_bill_get(request):
    """Return current draft bill for the logged-in user."""
    try:
        draft = DraftBill.objects.get(delivery_user=request.user)
        res = {
            'has_draft': True,
            'items': draft.items_json,
            'store_name': draft.store_name,
            'old_balance': str(draft.old_balance),
        }
        edit_order_id = draft.items_json.get('_edit_order_id')
        if edit_order_id:
            try:
                order = Order.objects.get(id=edit_order_id)
                res['editing_order_unpaid_balance'] = float(order.remaining_balance) if order.remaining_balance is not None else float(order.grand_total)
                res['editing_order_old_balance'] = float(order.old_balance)
                res['editing_order_store_name'] = order.store_name
            except Order.DoesNotExist:
                pass
        return JsonResponse(res)
    except DraftBill.DoesNotExist:
        return JsonResponse({'has_draft': False})


@login_required
@require_POST
def draft_bill_save(request):
    """Save or update the current draft bill for the logged-in user."""
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
    """Delete the current draft bill for the logged-in user."""
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
            'raw_status': order.status,
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

@login_required
def order_edit_details_api(request, order_id):
    if request.user.role != 'delivery':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
        
    items = []
    for item in order.items.all():
        items.append({
            'product_id': item.product_id,
            'quantity': item.quantity,
            'price': float(item.price_at_time)
        })
        
    return JsonResponse({
        'id': order.id,
        'store_name': order.store_name,
        'old_balance': float(order.old_balance),
        'remaining_balance': float(order.remaining_balance) if order.remaining_balance is not None else float(order.grand_total),
        'items': items
    })


@login_required
@require_POST
def customer_quick_bill_create(request):
    """Allow a logged-in customer to place a new order via the popup quick-bill UI."""
    start_time = time.time()
    
    if request.user.role != 'customer':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    # Extract items from POST
    items = []
    for key, value in request.POST.items():
        if key.startswith('qty_'):
            try:
                product_id = int(key.split('_')[1])
                qty = int(value)
                if qty > 0:
                    product = Product.objects.filter(id=product_id, available=True).first()
                    if product:
                        price = Decimal(str(product.price))
                        items.append((product, qty, price))
            except (ValueError, IndexError):
                continue

    if not items:
        return JsonResponse({'success': False, 'error': 'Please select at least one item.'})

    # Respect item order
    item_order_str = request.POST.get('item_order', '').strip()
    if item_order_str:
        try:
            ordered_ids = [int(x) for x in item_order_str.split(',') if x.strip()]
            items.sort(key=lambda x: ordered_ids.index(x[0].id) if x[0].id in ordered_ids else 999)
        except ValueError:
            pass

    try:
        with transaction.atomic():
            total_amount = sum(price * q for p, q, price in items)
            customer = request.user
            store_name = customer.store_name or customer.name or customer.username
            
            from django.db.models import Sum, F
            from django.db.models.functions import Coalesce
            
            old_balance = Order.objects.filter(
                payment_status='unpaid',
                customer=customer
            ).exclude(status='cancelled').aggregate(
                balance=Sum(Coalesce('remaining_balance', F('total_amount') + F('old_balance')))
            )['balance'] or Decimal('0.00')

            order = Order.objects.create(
                customer=customer,
                store_name=store_name,
                status='pending',
                total_amount=total_amount,
                old_balance=old_balance,
                original_old_balance=old_balance,
                remaining_balance=total_amount + old_balance,
                payment_status='unpaid',
                processing_time_ms=int((time.time() - start_time) * 1000)
            )

            for product, qty, price in items:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price_at_time=price
                )
                
            if old_balance > 0:
                prior_unpaid = Order.objects.filter(
                    customer=customer,
                    payment_status='unpaid'
                ).exclude(status='cancelled').exclude(id=order.id)
                prior_unpaid.update(
                    payment_status='paid',
                    remaining_balance=Decimal('0.00')
                )

        return JsonResponse({'success': True, 'message': f'✓ Order #{order.id} placed successfully!'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': 'An error occurred while placing the order.'})

