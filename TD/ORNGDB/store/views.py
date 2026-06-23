from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Store

# Helper to ensure user is an agent
is_agent = lambda u: u.is_authenticated and u.role == 'agent'

@login_required
@user_passes_test(is_agent)
def store_list(request):
    stores = Store.objects.filter(agent=request.user)
    return render(request, 'store/store_list.html', {'stores': stores})

@login_required
@user_passes_test(is_agent)
def store_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        if name and phone:
            Store.objects.create(name=name, phone=phone, agent=request.user)
            return redirect('store_list')
    return render(request, 'store/store_form.html')

@login_required
@user_passes_test(is_agent)
def store_update(request, store_id):
    store = get_object_or_404(Store, pk=store_id, agent=request.user)
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        if name:
            store.name = name
        if phone:
            store.phone = phone
        store.save()
        return redirect('store_list')
    return render(request, 'store/store_form.html', {'store': store})

@login_required
@user_passes_test(is_agent)
def store_delete(request, store_id):
    store = get_object_or_404(Store, pk=store_id, agent=request.user)
    if request.method == 'POST':
        store.delete()
        return redirect('store_list')
    return render(request, 'store/store_confirm_delete.html', {'store': store})
