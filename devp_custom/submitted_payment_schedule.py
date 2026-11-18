import frappe
from erpnext.controllers.accounts_controller import get_payment_terms
from frappe import _
from frappe.utils import flt, getdate


SCHEDULE_INPUTS = ("due_date", "invoice_portion")
SCHEDULE_AMOUNTS = ("payment_amount", "base_payment_amount", "outstanding", "base_outstanding")
SCHEDULE_FIELDS = SCHEDULE_INPUTS + SCHEDULE_AMOUNTS


def payment_schedule_blocker(invoice, *, for_update=False):
    if (
        invoice.is_pos or invoice.is_return or invoice.get("is_opening") == "Yes"
        or flt(invoice.grand_total) <= 0 or not invoice.due_date
    ):
        return _("This invoice does not support post-submission schedule changes.")

    total, base_total = invoice.get_payment_schedule_grand_totals()
    party_total = base_total if invoice.party_account_currency == invoice.company_currency else total
    precision = invoice.precision("outstanding_amount")
    if (
        flt(invoice.total_advance) or flt(invoice.write_off_amount)
        or flt(invoice.outstanding_amount, precision) != flt(party_total, precision)
        or any(row.paid_amount or row.base_paid_amount or row.discounted_amount for row in invoice.payment_schedule)
    ):
        return _("This invoice has a payment, advance, credit or write-off. Ask Accounts to review its allocations before changing the schedule.")

    active = ("in", [0, 1])
    references = (
        ("Payment Entry Reference", {"reference_doctype": invoice.doctype, "reference_name": invoice.name, "docstatus": active}),
        ("Payment Request", {"reference_doctype": invoice.doctype, "reference_name": invoice.name, "docstatus": active}),
        ("Overdue Payment", {"sales_invoice": invoice.name, "docstatus": active}),
        ("Payment Ledger Entry", {
            "against_voucher_type": invoice.doctype, "against_voucher_no": invoice.name,
            "voucher_no": ("!=", invoice.name), "delinked": 0,
        }),
    )
    for doctype, filters in references:
        if frappe.db.get_value(doctype, filters, "name", for_update=for_update):
            return _("A payment, allocation, payment request or dunning references this invoice. Ask Accounts to review the linked records before changing its schedule.")
    return ""


def load_payment_schedule_state(invoice, method=None):
    if invoice.docstatus == 1:
        invoice.set_onload("devp_schedule_blocker", payment_schedule_blocker(invoice))
        invoice.set_onload("devp_schedule_template", invoice.payment_terms_template or "")


def requires_due_date_amendment(invoice, due_date, *, for_update=False):
    if getdate(due_date) == getdate(invoice.due_date):
        return False
    if invoice.get("irn"):
        return True

    for doctype, active_field in (("GL Entry", "is_cancelled"), ("Payment Ledger Entry", "delinked")):
        if frappe.db.get_value(doctype, [
            ["voucher_type", "=", invoice.doctype],
            ["voucher_no", "=", invoice.name],
            ["account", "=", invoice.debit_to],
            [active_field, "=", 0],
            ["due_date", "is", "set"],
            ["due_date", "!=", due_date],
        ], "name", for_update=for_update):
            return True
    return False


def schedule_values(row):
    return row.get_valid_dict(convert_dates_to_str=True)


def schedule_changed(rows, previous, fields):
    if [row.name for row in rows] != [row.name for row in previous]:
        return True
    return any(
        any((new.get(field) or None) != (old.get(field) or None) for field in fields)
        for new, old in ((schedule_values(row), schedule_values(old)) for row, old in zip(rows, previous, strict=True))
    )


def require_editable_schedule(invoice, *, for_update=False):
    if invoice.docstatus != 1:
        frappe.throw(_("Select a submitted Sales Invoice."))
    if message := payment_schedule_blocker(invoice, for_update=for_update):
        frappe.throw(message)


def calculate_schedule(invoice, template, rows=None):
    total, base_total = invoice.get_payment_schedule_grand_totals()
    replacing = bool(template and template != invoice.payment_terms_template)
    if replacing:
        calculated = [
            frappe.new_doc("Payment Schedule", parent_doc=invoice, parentfield="payment_schedule").update(row)
            for row in get_payment_terms(template, invoice.posting_date, total, base_total)
        ]
    else:
        calculated = [frappe.get_doc(row.as_dict()) for row in invoice.payment_schedule]
        if rows is not None:
            if [row.get("name") for row in rows] != [row.name for row in calculated]:
                frappe.throw(_("Edit the existing payment rows. To replace rows, select a different Payment Terms Template."))
            for row, values in zip(calculated, rows, strict=True):
                row.update({field: values.get(field) for field in SCHEDULE_INPUTS})

    if not calculated:
        frappe.throw(_("Select a Payment Terms Template to create a schedule."))
    if template and frappe.db.get_value("Payment Terms Template", template, "allocate_payment_based_on_payment_terms"):
        terms = [row.payment_term for row in calculated]
        if not all(terms) or len(set(terms)) != len(terms):
            frappe.throw(_("Use a different Payment Term for each row when the template allocates payments by term."))

    posting_date = getdate(invoice.posting_date)
    portion_precision = calculated[0].precision("invoice_portion")
    for row in calculated:
        row.invoice_portion = flt(row.invoice_portion, portion_precision)
        if not (0 < row.invoice_portion <= 100):
            frappe.throw(_("Every Invoice Portion must be greater than zero and at most 100%."))
        if not row.due_date or getdate(row.due_date) < posting_date:
            frappe.throw(_("Payment Schedule due dates must be on or after the invoice posting date."))
        row.due_date = getdate(row.due_date)

    if flt(sum(row.invoice_portion for row in calculated), portion_precision) != 100:
        frappe.throw(_("Invoice Portions must add up to 100%."))
    for field, amount in (("payment_amount", total), ("base_payment_amount", base_total)):
        precision = calculated[0].precision(field)
        remaining = flt(amount, precision)
        for row in calculated:
            value = flt(amount * row.invoice_portion / 100, precision)
            row.set(field, value)
            remaining -= value
        last = calculated[-1]
        last.set(field, flt(last.get(field) + remaining, precision))
        if any(row.get(field) <= 0 for row in calculated):
            frappe.throw(_("Every payment row must have a positive amount in both currencies."))

    for row in calculated:
        invoice.set_term_outstanding(row, keep_settled=False)
    original = invoice.payment_schedule
    try:
        invoice.payment_schedule = calculated
        invoice.validate_payment_schedule_dates()
        invoice.validate_payment_schedule_amount()
    finally:
        invoice.payment_schedule = original
    return calculated


@frappe.whitelist(methods=["POST"])
def preview_payment_schedule(invoice_name: str, template: str | None = None, rows: str | list | None = None):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    for permission in ("read", "write", "submit"):
        invoice.check_permission(permission)
    require_editable_schedule(invoice)
    rows = frappe.parse_json(rows) if rows is not None else None
    if rows is not None and (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)):
        frappe.throw(_("Provide a list of existing payment rows."))
    calculated = calculate_schedule(invoice, template, rows)
    due_date = max(row.due_date for row in calculated)
    return {
        "rows": [row.as_dict() for row in calculated],
        "due_date": due_date,
        "requires_amendment": requires_due_date_amendment(invoice, due_date),
    }


def validate_payment_schedule_update(invoice, method=None):
    previous = invoice.get_doc_before_save()
    if not previous or not invoice.meta.get_field("payment_schedule").allow_on_submit:
        return
    rows = invoice.payment_schedule
    original = previous.payment_schedule
    changed_template = (invoice.payment_terms_template or "") != (previous.payment_terms_template or "")
    meta = frappe.get_meta("Payment Schedule")
    fields = {df.fieldname for df in meta.fields}.intersection(meta.get_valid_columns())
    if not changed_template and not schedule_changed(rows, original, fields):
        current_due_date = getdate(invoice.due_date) if invoice.due_date else None
        previous_due_date = getdate(previous.due_date) if previous.due_date else None
        if current_due_date != previous_due_date:
            frappe.throw(_("Change the due date through the Payment Schedule."))
        return

    invoice.check_permission("submit")
    require_editable_schedule(previous, for_update=True)
    template = invoice.payment_terms_template
    replacing = bool(template and changed_template)
    if not replacing and schedule_changed(rows, original, fields.difference(SCHEDULE_FIELDS)):
        frappe.throw(_("Only due dates and invoice portions can be edited on existing payment rows. To replace rows, select a different Payment Terms Template."))

    values = [schedule_values(row) for row in rows] if not replacing else None
    calculated = calculate_schedule(previous, template, values)
    due_date = max(row.due_date for row in calculated)
    if requires_due_date_amendment(previous, due_date, for_update=True):
        frappe.throw(_(
            "The proposed due date differs from a posted receivable date or belongs to an invoice with an IRN. "
            "Use Prepare Due Date Amendment to carry this schedule into an amended invoice."
        ))
    invoice.due_date = due_date
    if replacing:
        invoice.set("payment_schedule", [row.get_valid_dict(ignore_nulls=True) for row in calculated])
        invoice.set_parent_in_children()
        invoice.set_name_in_children()
    else:
        for row, computed in zip(rows, calculated, strict=True):
            row.update({field: computed.get(field) for field in SCHEDULE_FIELDS})


def preserve_other_payment_schedules(doc, method=None):
    if doc.doctype == "Sales Invoice" or doc.flags.ignore_validate_update_after_submit:
        return
    field = doc.meta.get_field("payment_schedule")
    previous = doc.get_doc_before_save()
    if field and field.options == "Payment Schedule" and previous:
        old_rows = {row.name: row for row in previous.payment_schedule}
        for row in doc.payment_schedule:
            if row.name in old_rows and schedule_changed([row], [old_rows[row.name]], SCHEDULE_FIELDS):
                frappe.throw(_("Editing submitted payment schedule rows is available on eligible Sales Invoices."), frappe.UpdateAfterSubmitError)
