from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .selectors import (
    DEFAULT_DIR,
    DEFAULT_SORT,
    SORT_FIELD_MAP,
    get_customer_by_display_id,
    get_customer_collect_context,
    get_customer_detail_context,
    get_customer_list_context,
    get_customer_table_context,
    get_record_borrowed_context,
    get_record_debt_context,
)
from .services import (
    create_customer,
    delete_customer,
    record_customer_borrowed,
    record_customer_debt,
)


# ---------------------------------------------------------------------------
# Accent colour mapping for summary cards.
# Maps the `accent` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour).
# ---------------------------------------------------------------------------
_ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def _apply_accent(stats: list[dict]) -> None:
    """Mutates stat dicts in place, adding ``border_class`` and ``icon_class``."""
    for stat in stats:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_list_view(request):
    """Renders the full Customers page with Summary, Debt, and Ranking tabs."""
    context = get_customer_list_context(request.user)
    _apply_accent(context["stats"])
    _apply_accent(context["debt_stats"])
    _apply_accent(context["ranking_stats"])
    return render(request, "customers/customer_list.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_table_view(request):
    """HTMX endpoint — returns the sorted customer table partial."""
    sort_field = request.GET.get("sort", DEFAULT_SORT)
    sort_field = sort_field if sort_field in SORT_FIELD_MAP else DEFAULT_SORT
    direction = request.GET.get("dir", DEFAULT_DIR)
    direction = direction if direction in ("asc", "desc") else DEFAULT_DIR
    context = get_customer_table_context(request.user, sort_field, direction)
    return render(request, "customers/partials/customer_table.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_detail_view(request, customer_id: str):
    """HTMX endpoint — returns the customer detail modal partial."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)
    context = get_customer_detail_context(customer)
    return render(request, "customers/partials/detail_modal.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_collect_view(request, customer_id: str):
    """HTMX endpoint — returns the collect modal partial grouped by rider."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)
    context = get_customer_collect_context(customer)
    return render(request, "customers/partials/collect_modal.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_add_view(request):
    """HTMX endpoint — returns the add-customer modal partial."""
    return render(request, "customers/partials/add_customer_modal.html")


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_add_submit_view(request):
    """HTMX endpoint — creates a new customer."""
    try:
        customer = create_customer(
            name=request.POST.get("name", ""),
            contact_number=request.POST.get("contact_number", ""),
            address=request.POST.get("address", ""),
            credit_limit=request.POST.get("credit_limit", ""),
            performed_by=request.user,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": " ".join(e.messages)},
            status=400,
        )

    message = f'Customer "{customer.name}" added.'
    return render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def record_debt_view(request):
    """HTMX endpoint — returns the record-debt modal partial."""
    context = get_record_debt_context(request.user)
    return render(request, "customers/partials/record_debt_modal.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def record_debt_submit_view(request):
    """HTMX endpoint — records a new customer credit line."""
    try:
        credit_line = record_customer_debt(
            customer_id=request.POST.get("customer_id", ""),
            product_key=request.POST.get("product_key", ""),
            qty_credited=request.POST.get("qty_credited", ""),
            unit_price=request.POST.get("unit_price", ""),
            performed_by=request.user,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": " ".join(e.messages)},
            status=400,
        )

    customer = credit_line.customer
    customer_id = request.POST.get("customer_id", "")
    message = (
        f"Recorded {credit_line.qty_credited} credited unit(s) "
        f"for {customer_id}."
    )
    return render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def record_borrowed_view(request):
    """HTMX endpoint — returns the record-borrowed-item modal partial."""
    context = get_record_borrowed_context(request.user)
    return render(
        request, "customers/partials/record_borrowed_modal.html", context
    )


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def record_borrowed_submit_view(request):
    """HTMX endpoint — records containers borrowed by a customer."""
    customer_id = request.POST.get("customer_id", "")
    qty_borrowed = request.POST.get("qty_borrowed", "")
    try:
        record_customer_borrowed(
            customer_id=customer_id,
            container_key=request.POST.get("container_key", ""),
            qty_borrowed=qty_borrowed,
            performed_by=request.user,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": " ".join(e.messages)},
            status=400,
        )

    message = (
        f"Recorded {qty_borrowed} borrowed container(s) "
        f"for {customer_id}."
    )
    return render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_delete_view(request, customer_id: str):
    """HTMX endpoint — soft-deletes a customer when safe to do so."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    try:
        delete_customer(customer=customer, performed_by=request.user)
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": " ".join(e.messages)},
            status=400,
        )

    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Customer {customer_id} deleted."},
    )
    response["HX-Redirect"] = "/customers/"
    return response
