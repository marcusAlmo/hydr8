from django.shortcuts import render

# Create your views here.
def index(request):
    """
    Renders the initial landing page for the application.
    """
    return render(request, 'users/index.html')