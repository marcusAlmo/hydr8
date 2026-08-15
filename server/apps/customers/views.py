import json
from functools import wraps

from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import error_message
from apps.settings.selectors import get_default_credit_limit
from apps.users.permissions import is_back_office

from .selectors import (
    DEFAULT_DIR,
    DEFAULT_SORT,
    SORT_FIELD_MAP,
    get_customer_by_display_id,
    get_customer_collect_context,
    get_customer_detail_context,
    get_customer_edit_context,
    get_customer_list_context,
    get_customer_table_context,
    get_record_borrowed_context,
    get_record_debt_context,
)
from .services import (
    create_customer,
    delete_customer,
    record_customer_borrowed,
    record_customer_collection,
    record_customer_debt,
    update_customer,
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


def _success_response(
    request,
    message: str,
    *,
    refresh_table: bool = False,
):
    """Returns the form-success partial (close-modal script) with an
    ``HX-Trigger`` that fires ``showToast`` (rendered client-side via
    ``hydr8ShowToast``) and optionally ``refreshCustomerTable``.

    The toast is triggered via HX-Trigger instead of an OOB swap because
    OOB swaps are unreliable when the main swap target (``#form-error``)
    lives inside a modal that closes itself immediately after the
    response is processed.
    """
    response = render(request, "customers/partials/form_success.html", {})
    trigger: dict = {
        "showToast": {"msg": message, "type": "success"},
    }
    if refresh_table:
        trigger["refreshCustomerTable"] = ""
    response["HX-Trigger"] = json.dumps(trigger)
    return response


def _back_office_required(view):
    """Decorator that restricts a view to Admin or Staff (back-office) users."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_back_office(request.user):
            return HttpResponse("Forbidden", status=403)
        return view(request, *args, **kwargs)
    return wrapper


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_list_view(request):
    """Renders the full Customers page with Summary and Ranking tabs."""
    context = get_customer_list_context(request.user)
    _apply_accent(context["stats"])
    _apply_accent(context["ranking_stats"])
    return render(request, "customers/customer_list.html", context)


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_table_view(request):
    """HTMX endpoint — returns the sorted/filtered customer table partial."""
    sort_field = request.GET.get("sort", DEFAULT_SORT)
    sort_field = sort_field if sort_field in SORT_FIELD_MAP else DEFAULT_SORT
    direction = request.GET.get("dir", DEFAULT_DIR)
    direction = direction if direction in ("asc", "desc") else DEFAULT_DIR
    query = request.GET.get("q", "")
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    context = get_customer_table_context(request.user, sort_field, direction, query, page)
    return render(request, "customers/partials/customer_table.html", context)


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_detail_view(request, customer_id: str):
    """HTMX endpoint — returns the customer detail modal partial."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)
    context = get_customer_detail_context(customer, user=request.user)
    return render(request, "customers/partials/detail_modal.html", context)


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_edit_view(request, customer_id: str):
    """HTMX endpoint — returns the edit-customer modal partial."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)
    context = get_customer_edit_context(customer)
    return render(request, "customers/partials/edit_customer_modal.html", context)


@login_required
@_back_office_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_edit_submit_view(request, customer_id: str):
    """HTMX endpoint — updates an existing customer."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    try:
        update_customer(
            customer=customer,
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
            {"message": error_message(e)},
            status=400,
        )

    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Customer {customer_id} updated."},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": f"Customer {customer_id} updated.", "type": "success"},
        "refreshCustomerTable": "",
    })
    return response


@login_required
@_back_office_required
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
@_back_office_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_collect_submit_view(request, customer_id: str):
    """HTMX endpoint — records a customer collection (returns + payments)."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    # Parse prefixed POST fields into structured lists.
    #   returned_BC-{pk}  → container return quantity
    #   qty_paid_CL-{pk}   → units paid on a credit line
    #   amount_paid_CL-{pk}→ peso amount paid on a credit line
    returns: list[dict] = []
    payments: list[dict] = []
    for key, value in request.POST.items():
        if key.startswith("returned_BC-"):
            returns.append({
                "borrowed_id": key[len("returned_BC-"):],
                "qty": value,
            })
        elif key.startswith("qty_paid_CL-"):
            cl_id = key[len("qty_paid_CL-"):]
            payments.append({
                "credit_line_id": cl_id,
                "qty_paid": value,
                "amount": request.POST.get(f"amount_paid_CL-{cl_id}", "0"),
            })

    try:
        result = record_customer_collection(
            customer_id=customer_id,
            performed_by=request.user,
            returns=returns,
            payments=payments,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": error_message(e)},
            status=400,
        )

    parts = []
    if result["returns_recorded"] > 0:
        parts.append(f"{result['returns_recorded']} container(s) returned")
    if result["total_collected"] > 0:
        parts.append(f"₱{result['total_collected']} collected")
    message = (
        f"Recorded {' and '.join(parts)} for {customer_id}."
        if parts
        else "No changes recorded."
    )
    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": message, "type": "success"},
        "refreshCustomerTable": "",
    })
    return response


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_add_view(request):
    """HTMX endpoint — returns the add-customer modal partial.

    Pre-populates the credit limit field with the tenant's default
    ``approved_credit_limit`` from System Config so operators don't have
    to re-enter the same ceiling for every customer.  The value is
    editable — operators can override it per customer at creation time.
    """
    context = {
        "default_credit_limit": get_default_credit_limit(request.user),
    }
    return render(request, "customers/partials/add_customer_modal.html", context)


@login_required
@_back_office_required
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
            {"message": error_message(e)},
            status=400,
        )

    message = f'Customer "{customer.name}" added.'
    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": message, "type": "success"},
        "refreshCustomerTable": "",
    })
    return response


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def record_debt_view(request):
    """HTMX endpoint — returns the record-debt modal partial."""
    context = get_record_debt_context(request.user)
    return render(request, "customers/partials/record_debt_modal.html", context)


@login_required
@_back_office_required
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
            care_of_id=request.POST.get("care_of_id", ""),
            customer_name=request.POST.get("customer_name", ""),
            transaction_date=request.POST.get("transaction_date", ""),
            performed_by=request.user,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": error_message(e)},
            status=400,
        )

    customer = credit_line.customer
    customer_id = request.POST.get("customer_id", "")
    message = (
        f"Recorded {credit_line.qty_credited} credited unit(s) "
        f"for {customer_id}."
    )
    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": message, "type": "success"},
        "refreshCustomerTable": "",
    })
    return response


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def record_borrowed_view(request):
    """HTMX endpoint — returns the record-borrowed-item modal partial."""
    context = get_record_borrowed_context(request.user)
    return render(
        request, "customers/partials/record_borrowed_modal.html", context
    )


@login_required
@_back_office_required
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
            care_of_id=request.POST.get("care_of_id", ""),
            customer_name=request.POST.get("customer_name", ""),
            transaction_date=request.POST.get("transaction_date", ""),
            performed_by=request.user,
        )
    except ValidationError as e:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": error_message(e)},
            status=400,
        )

    message = (
        f"Recorded {qty_borrowed} borrowed container(s) "
        f"for {customer_id}."
    )
    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": message, "type": "success"},
        "refreshCustomerTable": "",
    })
    return response


@login_required
@_back_office_required
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
            {"message": error_message(e)},
            status=400,
        )

    # Return toast + close-modal script (form_success.html). The row was
    # already faded out optimistically via the customer-deleting event;
    # the modal closes via the script. No HX-Redirect — the row is
    # visually gone and will be absent on the next table refresh.
    message = f"Customer {customer_id} deleted."
    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": message},
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": message, "type": "success"},
        "refreshCustomerTable": "",
    })
    return response
