import json
import re
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import error_message
from apps.settings.selectors import get_default_credit_limit
from apps.users.permissions import is_admin, is_back_office

from .models import BorrowedContainer, CreditLine, CreditPayment
from .selectors import (
    DEFAULT_DIR,
    DEFAULT_SORT,
    SORT_FIELD_MAP,
    get_customer_by_display_id,
    get_customer_collect_context,
    get_customer_detail_context,
    get_customer_edit_context,
    get_customer_history_context,
    get_customer_list_context,
    get_customer_table_context,
    get_prompt_returner_count,
    get_prompt_returners,
    get_record_borrowed_context,
    get_record_debt_context,
    get_top_payer_count,
    get_top_payers,
)
from .services import (
    create_customer,
    delete_borrowed_container,
    delete_credit_line,
    delete_credit_payment,
    delete_customer,
    edit_borrowed_container,
    edit_credit_line,
    edit_credit_payment,
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
def top_payers_view(request):
    """HTMX endpoint — returns the full Top Payers leaderboard."""
    top_payers = get_top_payers(request.user, limit=None)
    return render(
        request,
        "customers/partials/top_payers_card.html",
        {
            "top_payers": top_payers,
            "payer_count": get_top_payer_count(request.user),
            "view_all": True,
        },
    )


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def prompt_returners_view(request):
    """HTMX endpoint — returns the full Prompt Returners leaderboard."""
    prompt_returners = get_prompt_returners(request.user, limit=None)
    return render(
        request,
        "customers/partials/prompt_returners_card.html",
        {
            "prompt_returners": prompt_returners,
            "returner_count": get_prompt_returner_count(request.user),
            "view_all": True,
        },
    )


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
    #   returned_BC-{pk}      → container return quantity
    #   returned_at_BC-{pk}   → date the return was recorded
    #   qty_paid_CL-{pk}      → units paid on a credit line
    #   amount_paid_CL-{pk}   → peso amount paid on a credit line
    #   paid_at_CL-{pk}       → date the payment was made
    returns: list[dict] = []
    payments: list[dict] = []
    for key, value in request.POST.items():
        if key.startswith("returned_BC-"):
            borrowed_id = key[len("returned_BC-"):]
            returns.append({
                "borrowed_id": borrowed_id,
                "qty": value,
                "returned_at": request.POST.get(f"returned_at_BC-{borrowed_id}", ""),
            })
        elif key.startswith("qty_paid_CL-"):
            cl_id = key[len("qty_paid_CL-"):]
            payments.append({
                "credit_line_id": cl_id,
                "qty_paid": value,
                "amount": request.POST.get(f"amount_paid_CL-{cl_id}", "0"),
                "paid_at": request.POST.get(f"paid_at_CL-{cl_id}", ""),
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


# ---------------------------------------------------------------------------
# Customer ledger history and edit views
# ---------------------------------------------------------------------------

def _parse_history_item_id(item_id: str) -> tuple[str, int]:
    """Parses a ledger display id (``CL-1``, ``CP-1``, ``BC-1``) into (kind, pk)."""
    m = re.fullmatch(r"(CL|CP|BC)-(\d+)", (item_id or "").strip().upper())
    if not m:
        return "", 0
    return m.group(1), int(m.group(2))


def _get_history_item(user, customer, kind: str, pk: int):
    """Resolves the model instance for a history display id scoped to a customer."""

    if kind == "CL":
        return (
            CreditLine.objects
            .for_user(user)
            .select_related("product", "care_of", "company")
            .filter(pk=pk, customer=customer)
            .first()
        )
    if kind == "CP":
        return (
            CreditPayment.objects
            .for_user(user)
            .select_related("credit_line__product", "remittance", "recorded_by", "company")
            .filter(pk=pk, credit_line__customer=customer)
            .first()
        )
    if kind == "BC":
        return (
            BorrowedContainer.objects
            .for_user(user)
            .select_related("care_of", "recorded_by", "company")
            .filter(pk=pk, customer=customer)
            .first()
        )
    return None


def _history_item_context(item) -> dict:
    """Builds the minimal context for an edit form from the resolved model."""

    if isinstance(item, CreditLine):
        return {
            "kind": "credit_line",
            "display_id": f"CL-{item.pk}",
            "qty_credited": item.qty_credited,
            "unit_price": str(item.unit_price_snapshot),
            "transaction_date": item.transaction_date.isoformat(),
        }
    if isinstance(item, CreditPayment):
        return {
            "kind": "credit_payment",
            "display_id": f"CP-{item.pk}",
            "qty_paid": item.containers_paid,
            "amount": str(item.amount),
            "transaction_date": (
                item.paid_at.isoformat()
                if item.paid_at
                else item.created_at.strftime("%Y-%m-%d")
            ),
        }
    if isinstance(item, BorrowedContainer):
        return {
            "kind": "borrowed",
            "display_id": f"BC-{item.pk}",
            "qty_borrowed": item.qty_borrowed,
            "qty_returned": item.qty_returned,
            "transaction_date": item.transaction_date.isoformat(),
        }
    return {}


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_history_view(request, customer_id: str):
    """HTMX endpoint — returns the customer ledger history tab."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)
    context = get_customer_history_context(customer, request.user)
    return render(request, "customers/partials/customer_history.html", context)


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def customer_history_edit_view(request, customer_id: str, item_id: str):
    """HTMX endpoint — returns the edit form for a single ledger entry."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    kind, pk = _parse_history_item_id(item_id)
    if not kind:
        return HttpResponse("Record not found.", status=404)
    display_id = f"{kind}-{pk}"
    item = _get_history_item(request.user, customer, kind, pk)
    if item is None:
        return HttpResponse("Record not found.", status=404)

    context = {
        "customer_id": customer_id,
        "item_id": display_id,
        "item": _history_item_context(item),
    }
    return render(request, "customers/partials/history_edit_form.html", context)


@login_required
@_back_office_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_history_edit_submit_view(request, customer_id: str, item_id: str):
    """HTMX endpoint — applies a ledger edit after PIN verification."""
    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    kind, pk = _parse_history_item_id(item_id)
    if not kind:
        return HttpResponse("Record not found.", status=404)
    display_id = f"{kind}-{pk}"
    pin = request.POST.get("pin", "")
    transaction_date = request.POST.get("transaction_date", "")
    try:
        if kind == "CL":
            edit_credit_line(
                credit_line_id=str(pk),
                customer=customer,
                qty_credited=request.POST.get("qty_credited", ""),
                unit_price=request.POST.get("unit_price", ""),
                transaction_date=transaction_date,
                pin=pin,
                performed_by=request.user,
            )
        elif kind == "CP":
            edit_credit_payment(
                payment_id=str(pk),
                customer=customer,
                qty_paid=request.POST.get("qty_paid", ""),
                amount=request.POST.get("amount", ""),
                transaction_date=transaction_date,
                pin=pin,
                performed_by=request.user,
            )
        elif kind == "BC":
            edit_borrowed_container(
                borrowed_id=str(pk),
                customer=customer,
                qty_borrowed=request.POST.get("qty_borrowed", ""),
                qty_returned=request.POST.get("qty_returned", ""),
                transaction_date=transaction_date,
                pin=pin,
                performed_by=request.user,
            )
        else:
            raise ValidationError("Invalid record reference.")
    except ValidationError as e:
        msg = error_message(e)
        item = _get_history_item(request.user, customer, kind, pk)
        if item is not None:
            response = render(
                request,
                "customers/partials/history_edit_form.html",
                {
                    "customer_id": customer_id,
                    "item_id": display_id,
                    "item": _history_item_context(item),
                    "error": msg,
                },
                status=400,
            )
            response["HX-Retarget"] = f"#history-item-{display_id}"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps(
                {"showToast": {"msg": msg, "type": "error"}}
            )
            return response
        response = render(
            request,
            "customers/partials/form_error.html",
            {"message": msg},
            status=400,
        )
        response["HX-Trigger"] = json.dumps(
            {"showToast": {"msg": msg, "type": "error"}}
        )
        return response

    context = get_customer_history_context(customer, request.user)
    response = render(request, "customers/partials/customer_history.html", context)
    response["HX-Trigger"] = json.dumps(
        {"showToast": {"msg": "Record updated.", "type": "success"}}
    )
    return response


@login_required
@_back_office_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_history_delete_view(request, customer_id: str, item_id: str):
    """HTMX endpoint — returns the inline delete-confirm form for a ledger entry.

    Admin-only; non-admins receive a 403 so the delete button never
    appears for them in the first place (the template gates on
    ``is_deletable``), but this is a defense-in-depth check.
    """
    if not is_admin(request.user):
        return HttpResponse("Forbidden", status=403)

    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    kind, pk = _parse_history_item_id(item_id)
    if not kind:
        return HttpResponse("Record not found.", status=404)
    display_id = f"{kind}-{pk}"
    item = _get_history_item(request.user, customer, kind, pk)
    if item is None:
        return HttpResponse("Record not found.", status=404)

    context = {
        "customer_id": customer_id,
        "item_id": display_id,
        "item": _history_item_context(item),
    }
    return render(request, "customers/partials/history_delete_confirm.html", context)


@login_required
@_back_office_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def customer_history_delete_submit_view(request, customer_id: str, item_id: str):
    """HTMX endpoint — deletes a ledger entry after admin + PIN verification.

    Deletion is admin-only.  The service layer re-checks admin status and
    PIN, recomputes the customer's debt balance / aggregate counters, and
    blocks records linked to a remittance (PROTECT constraint).
    """
    if not is_admin(request.user):
        return HttpResponse("Forbidden", status=403)

    customer = get_customer_by_display_id(request.user, customer_id)
    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    kind, pk = _parse_history_item_id(item_id)
    if not kind:
        return HttpResponse("Record not found.", status=404)
    display_id = f"{kind}-{pk}"
    pin = request.POST.get("pin", "")
    try:
        if kind == "CL":
            delete_credit_line(
                credit_line_id=str(pk),
                customer=customer,
                pin=pin,
                performed_by=request.user,
            )
        elif kind == "CP":
            delete_credit_payment(
                payment_id=str(pk),
                customer=customer,
                pin=pin,
                performed_by=request.user,
            )
        elif kind == "BC":
            delete_borrowed_container(
                borrowed_id=str(pk),
                customer=customer,
                pin=pin,
                performed_by=request.user,
            )
        else:
            raise ValidationError("Invalid record reference.")
    except ValidationError as e:
        msg = error_message(e)
        item = _get_history_item(request.user, customer, kind, pk)
        if item is not None:
            response = render(
                request,
                "customers/partials/history_delete_confirm.html",
                {
                    "customer_id": customer_id,
                    "item_id": display_id,
                    "item": _history_item_context(item),
                    "error": msg,
                },
                status=400,
            )
            response["HX-Retarget"] = f"#history-item-{display_id}"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps(
                {"showToast": {"msg": msg, "type": "error"}}
            )
            return response
        response = render(
            request,
            "customers/partials/form_error.html",
            {"message": msg},
            status=400,
        )
        response["HX-Trigger"] = json.dumps(
            {"showToast": {"msg": msg, "type": "error"}}
        )
        return response

    context = get_customer_history_context(customer, request.user)
    response = render(request, "customers/partials/customer_history.html", context)
    response["HX-Trigger"] = json.dumps(
        {"showToast": {"msg": "Record deleted.", "type": "success"}}
    )
    return response
