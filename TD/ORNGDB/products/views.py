from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django import forms
from .models import Product, Store

# Helper to ensure user is an agent
is_agent = lambda u: u.is_authenticated and u.role == 'agent'

# Inline ModelForm for Product
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'purchase_price', 'selling_price', 'qty_available', 'store']
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        # Limit store choices to stores owned by this agent
        self.fields['store'].queryset = Store.objects.filter(agent=user)

@login_required
@user_passes_test(is_agent)
def product_list(request):
    products = Product.objects.filter(store__agent=request.user)
    return render(request, 'products/product_list.html', {'products': products})

@login_required
@user_passes_test(is_agent)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm(user=request.user)
    return render(request, 'products/product_form.html', {'form': form})

@login_required
@user_passes_test(is_agent)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, store__agent=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm(instance=product, user=request.user)
    return render(request, 'products/product_form.html', {'form': form, 'product': product})

@login_required
@user_passes_test(is_agent)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, store__agent=request.user)
    if request.method == 'POST':
        product.delete()
        return redirect('product_list')
    return render(request, 'products/product_confirm_delete.html', {'product': product})
