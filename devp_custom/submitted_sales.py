import frappe
from frappe import _
from frappe.utils import getdate


DOCTYPE_ITEMS = {"Sales Invoice": "Sales Invoice Item", "Delivery Note": "Delivery Note Item"}
TRANSPORT_FIELDS = (
    "transporter", "transporter_name", "gst_transporter_id", "driver", "driver_name",
    "lr_no", "lr_date", "vehicle_no", "distance", "mode_of_transport", "gst_vehicle_type",
)
BATCH_DATES = {
    "batch_manufacturing_date": "manufacturing_date",
    "batch_expiry_date": "expiry_date",
}
INFORMATIONAL_BATCH = "custom_informational_batch_no"


def batch_reference_field(doc, row):
    if not row.item_code:
        return None
    if row.get(INFORMATIONAL_BATCH):
        return INFORMATIONAL_BATCH
    if doc.doctype == "Sales Invoice" and frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
        return "batch_no"
    return INFORMATIONAL_BATCH


def batch_details(batch_no):
    batch = get_batch(batch_no) or {}
    return {"batch_no": batch_no, **{source: batch.get(source) for source in BATCH_DATES.values()}}


def informational_batch_details(row, primary_field):
    details = []
    seen = set()
    for field in (primary_field, INFORMATIONAL_BATCH, "batch_no"):
        batch_no = row.get(field) if field else None
        if not batch_no or batch_no in seen:
            continue
        if field == "batch_no" and not get_batch(batch_no):
            # The print hook may already have replaced this with a labelled value.
            continue
        seen.add(batch_no)
        details.append({"fieldname": field, **batch_details(batch_no)})
    return details


def has_reported_transport(doc):
    return doc.get("ewaybill") or doc.get("irn")


class SubmittedTransport:
    def set_fetch_from_value(self, doctype, df, values):
        # Do not let unrelated updates refresh reported values from Supplier or Driver.
        previous = self.get_doc_before_save()
        if (
            previous
            and previous.docstatus == 1
            and has_reported_transport(previous)
            and df.fieldname in TRANSPORT_FIELDS
        ):
            return
        return super().set_fetch_from_value(doctype, df, values)


def get_batch(batch_no):
    return frappe.get_cached_value(
        "Batch", batch_no, ("item", "manufacturing_date", "expiry_date", "disabled"), as_dict=True
    )


def bundle_batches(bundles):
    result = {}
    if bundles:
        for entry in frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": ("in", bundles), "batch_no": ("is", "set")},
            fields=["parent", "batch_no"],
        ):
            result.setdefault(entry.parent, set()).add(entry.batch_no)
    return result


def batch_allocations(doc):
    """Resolve posted batches by voucher detail, including linked deliveries and returns."""
    references = {row.name: {(doc.doctype, doc.name, row.name)} for row in doc.items}
    packed_rows = set()
    for packed in doc.get("packed_items", []):
        if packed.parent_detail_docname in references:
            packed_rows.add(packed.parent_detail_docname)
            references[packed.parent_detail_docname].add((doc.doctype, doc.name, packed.name))
    linked = {}
    for row in doc.items:
        if doc.doctype == "Sales Invoice":
            links = (
                ("Delivery Note", row.delivery_note, row.dn_detail),
                ("Sales Invoice", doc.return_against, row.sales_invoice_item),
            )
        else:
            links = (
                ("Sales Invoice", row.against_sales_invoice, row.si_detail),
                ("Delivery Note", doc.return_against, row.dn_detail),
            )
        for doctype, voucher, detail in links:
            if voucher and (doctype == "Delivery Note" or doc.is_return or (
                doc.doctype == "Delivery Note" and frappe.get_cached_value("Sales Invoice", voucher, "update_stock")
            )):
                linked.setdefault(row.name, set()).add((doctype, voucher))
                if detail:
                    references[row.name].add((doctype, voucher, detail))

    # An invoice can also be delivered later, with the link stored on the Delivery Note.
    if doc.doctype == "Sales Invoice" and references:
        for row in frappe.get_all(
            "Delivery Note Item",
            filters={"si_detail": ("in", list(references)), "docstatus": 1},
            fields=["name", "parent", "si_detail"],
        ):
            references[row.si_detail].add(("Delivery Note", row.parent, row.name))
            linked.setdefault(row.si_detail, set()).add(("Delivery Note", row.parent))

    keys = set().union(*references.values())
    ledger = {}
    bundles = {row.serial_and_batch_bundle for row in doc.items if row.serial_and_batch_bundle}
    if keys:
        for entry in frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "voucher_no": ("in", list({key[1] for key in keys})),
                "voucher_detail_no": ("in", list({key[2] for key in keys})),
                "is_cancelled": 0,
            },
            fields=["voucher_type", "voucher_no", "voucher_detail_no", "batch_no", "serial_and_batch_bundle"],
        ):
            key = (entry.voucher_type, entry.voucher_no, entry.voucher_detail_no)
            if key in keys:
                ledger.setdefault(key, []).append(entry)
                if entry.serial_and_batch_bundle:
                    bundles.add(entry.serial_and_batch_bundle)

    entries = bundle_batches(list(bundles))
    allocations = {}
    for row in doc.items:
        if doc.doctype == "Delivery Note":
            stock_voucher = row.name in packed_rows or frappe.get_cached_value("Item", row.item_code, "is_stock_item")
        else:
            stock_voucher = doc.update_stock
        own_key = (doc.doctype, doc.name, row.name)
        postings = ledger.get(own_key) or [
            entry for key in references[row.name] - {own_key} for entry in ledger.get(key, ())
        ]
        locked = bool(stock_voucher or postings or row.name in linked or row.serial_and_batch_bundle)
        if not locked:
            continue

        posted = set()
        for entry in postings:
            batches = entries.get(entry.serial_and_batch_bundle)
            if batches:
                posted.update(batches)
            elif entry.batch_no:
                posted.add(entry.batch_no)
        if not posted and (stock_voucher or row.serial_and_batch_bundle):
            posted.update(entries.get(row.serial_and_batch_bundle, ()))
            if not posted and row.batch_no and stock_voucher:
                posted.add(row.batch_no)
        vouchers = {(entry.voucher_type, entry.voucher_no) for entry in postings}
        if not vouchers:
            if stock_voucher:
                vouchers.add((doc.doctype, doc.name))
            else:
                vouchers.update(linked.get(row.name, ()))
        allocations[row.name] = frappe._dict(batches=sorted(posted), vouchers=sorted(vouchers))
    return allocations


def load_batch_allocations(doc, method=None):
    if doc.docstatus != 1:
        return
    data = {}
    informational = {}
    reference_details = {}
    allocations = batch_allocations(doc)
    for row in doc.items:
        allocation = allocations.get(row.name)
        if allocation is None:
            if row.item_code:
                field = batch_reference_field(doc, row)
                informational[row.name] = field
                details = informational_batch_details(row, field)
                reference_details[row.name] = details
                set_batch_dates(row, details[0]["batch_no"] if details else None)
            continue
        batches = allocation.batches
        set_batch_dates(row, batches[0] if len(batches) == 1 else None)
        if reference := row.get(INFORMATIONAL_BATCH):
            reference_details[row.name] = [{"fieldname": INFORMATIONAL_BATCH, **batch_details(reference)}]
        data[row.name] = {
            "show": bool(batches or row.batch_no or (
                row.item_code and frappe.get_cached_value("Item", row.item_code, "has_batch_no")
            )),
            "batches": [batch_details(batch_no) for batch_no in batches],
            "vouchers": [
                {"doctype": doctype, "name": name}
                for doctype, name in allocation.vouchers
                if (doctype, name) == (doc.doctype, doc.name)
                or frappe.has_permission(doctype, "read", doc=name)
            ],
        }
    doc.set_onload("devp_batch_allocations", data)
    doc.set_onload("devp_informational_batch_rows", list(informational))
    doc.set_onload("devp_informational_batch_fields", informational)
    doc.set_onload("devp_informational_batch_details", reference_details)


def show_posted_batches_in_print(doc, method=None, print_settings=None):
    if doc.docstatus != 1:
        return
    allocations = batch_allocations(doc)
    for row in doc.items:
        if row.name in allocations:
            batches = allocations[row.name].batches
            row.batch_no = ", ".join(batches)
            set_batch_dates(row, batches[0] if len(batches) == 1 else None)
        elif row.get(INFORMATIONAL_BATCH):
            details = informational_batch_details(row, INFORMATIONAL_BATCH)
            # Existing formats read this field. Label the printed value while keeping
            # the saved stock Batch No and all stock references separate.
            row.batch_no = _("Informational Batch Reference ({0})").format(
                ", ".join(detail["batch_no"] for detail in details)
            )
            set_batch_dates(row, details[0]["batch_no"] if len(details) == 1 else None)
        else:
            set_batch_dates(row, row.batch_no)


def set_batch_dates(row, batch_no):
    values = get_batch(batch_no) if batch_no else None
    for fieldname, source in BATCH_DATES.items():
        row.set(fieldname, (values or {}).get(source))


def set_draft_batch_dates(doc, method=None):
    bundles = list({row.serial_and_batch_bundle for row in doc.items if row.serial_and_batch_bundle})
    entries = bundle_batches(bundles)
    for row in doc.items:
        batches = entries.get(row.serial_and_batch_bundle, ())
        batch_no = next(iter(batches)) if len(batches) == 1 else row.batch_no if not batches else None
        if row.get(INFORMATIONAL_BATCH):
            if (
                doc.is_return or row.serial_and_batch_bundle or row.batch_no
                or (doc.doctype == "Sales Invoice" and doc.update_stock)
                or (doc.doctype == "Delivery Note" and frappe.get_cached_value("Item", row.item_code, "is_stock_item"))
            ):
                row.set(INFORMATIONAL_BATCH, None)
            else:
                batch_no = row.get(INFORMATIONAL_BATCH)
        set_batch_dates(row, batch_no)


def field_changed(doc, previous, fieldname):
    before, after = previous.get(fieldname), doc.get(fieldname)
    if not before or not after:
        return bool(before) != bool(after)
    return doc.has_value_changed(fieldname)


def validate_submitted_edit(doc, method=None):
    previous = doc.get_doc_before_save()
    if not previous or previous.docstatus != 1:
        return

    if [row.name for row in doc.items] != [row.name for row in previous.items]:
        frappe.throw(_("Submitted item rows cannot be added, removed or reordered."))

    template_changed = field_changed(doc, previous, "tc_name")
    terms_changed = field_changed(doc, previous, "terms")
    if template_changed or terms_changed:
        doc.check_permission("submit")
        if doc.tc_name and template_changed and not terms_changed:
            from erpnext.setup.doctype.terms_and_conditions.terms_and_conditions import get_terms_and_conditions

            doc.terms = get_terms_and_conditions(doc.tc_name, doc.as_dict())

    if has_reported_transport(previous) or has_reported_transport(doc):
        if any(field_changed(doc, previous, field) for field in TRANSPORT_FIELDS):
            frappe.throw(_(
                "Use Internal Transport Details for local updates. Use India Compliance actions "
                "to correct transport information reported on an e-Waybill or e-Invoice."
            ))

    allocations = batch_allocations(previous)
    for row, old_row in zip(doc.items, previous.items, strict=True):
        changed = {
            field for field in ("batch_no", INFORMATIONAL_BATCH)
            if (row.get(field) or "") != (old_row.get(field) or "")
        }
        if row.name in allocations:
            if changed:
                frappe.throw(_(
                    "Row {0}: This batch is linked to stock. Use Posted Batch Correction to amend "
                    "the stock document."
                ).format(row.idx))
            posted = allocations[row.name].batches
            set_batch_dates(row, posted[0] if len(posted) == 1 else None)
        else:
            field = batch_reference_field(previous, old_row)
            if changed.difference({field}):
                frappe.throw(_("Row {0}: Use the informational batch editor for this item.").format(row.idx))
            batch_no = row.get(field) if field else None
            if changed and batch_no:
                validate_batch_reference(doc, row, batch_no, old_row.item_code if field == "batch_no" else None)
            details = informational_batch_details(row, field)
            set_batch_dates(row, details[0]["batch_no"] if details else None)


def validate_batch_reference(doc, row, batch_no, item_code):
    batch = get_selectable_batch(batch_no)
    if batch.disabled:
        frappe.throw(_("Row {0}: Select an enabled Batch.").format(row.idx))
    if item_code and batch.item != item_code:
        frappe.throw(_("Row {0}: Select an enabled batch belonging to Item {1}.").format(row.idx, item_code))
    if not doc.is_return and batch.expiry_date and getdate(batch.expiry_date) < getdate(doc.posting_date):
        frappe.throw(_("Row {0}: The batch was expired on the posting date.").format(row.idx))


def get_selectable_batch(batch_no):
    batch = frappe.get_doc("Batch", batch_no)
    if not batch.has_permission("read"):
        batch.check_permission("select")
    return batch


@frappe.whitelist()
def get_batch_dates(batch_no: str | None = None, bundle: str | None = None):
    if bundle:
        frappe.get_doc("Serial and Batch Bundle", bundle).check_permission("read")
        batches = bundle_batches([bundle]).get(bundle, set())
        if len(batches) > 1:
            return {}
        if batches:
            batch_no = next(iter(batches))
    if not batch_no:
        return {}
    # Desk users with Batch Select can choose a batch without opening its master.
    batch = get_selectable_batch(batch_no)
    return {field: batch.get(field) for field in BATCH_DATES.values()}
