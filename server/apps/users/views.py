from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponse

def index(request):
    """
    Renders the initial landing page for the application.
    Passes an empty AuthenticationForm so the initial form can render without errors.
    """
    form = AuthenticationForm()
    return render(request, 'users/index.html', {'form': form})

def login_view(request):
    """
    Handles the HTMX login flow using industry standard Django Forms.
    - POST: Validates via AuthenticationForm. Returns failure state (form) or redirects.
    """
    if request.method == "POST":
        # Industry Standard: Rely on Django Forms for validation, sanitization, and auth
        form = AuthenticationForm(request, data=request.POST)
        
        if form.is_valid():
            # is_valid() ensures the user exists and the password is correct
            user = form.get_user()
            auth_login(request, user)
            
            # If successful, we tell HTMX to redirect the browser to the dashboard
            from django.urls import reverse
            response = HttpResponse()
            response['HX-Redirect'] = reverse('analytics:dashboard')
            return response
        else:
            # Login failed. Re-render the form with validation errors natively bound to it
            return render(request, 'users/partials/login_form.html', {
                'form': form
            })

    # GET request is typically no longer called directly since the form is in index.html,
    # but we provide a fresh form instance just in case.
    form = AuthenticationForm()
    return render(request, 'users/partials/login_form.html', {'form': form})