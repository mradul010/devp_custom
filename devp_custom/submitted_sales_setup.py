import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from devp_custom.submitted_payment_schedule import SCHEDULE_FIELDS
from devp_custom.submitted_sales import BATCH_DATES, DOCTYPE_ITEMS, INFORMATIONAL_BATCH, TRANSPORT_FIELDS


BATCH_ALLOCATION = "parent?.__onload?.devp_batch_allocations?.[doc.name]"
LOCKED_BATCH = f"Boolean({BATCH_ALLOCATION})"
BATCH_DETAILS_VISIBLE = (
    f"eval:Boolean({BATCH_ALLOCATION}?.show || parent?.__onload?.devp_informational_batch_rows?.includes(doc.name)"
    f" || (doc.docstatus === 1 && doc.{INFORMATIONAL_BATCH}))"
)
GOVERNMENT_TRANSPORT = "doc.docstatus === 1 && (doc.ewaybill || doc.irn)"


def get_property_setter_name(doctype, fieldname, prop):
    return frappe.db.get_value("Property Setter", {
        "doc_type": doctype,
        "field_name": fieldname if fieldname else ("is", "not set"),
        "property": prop,
    })


def set_property(meta, fieldname, prop, value, fieldtype, *, explicit=False):
    target = meta.get_field(fieldname) if fieldname else meta
    name = get_property_setter_name(meta.name, fieldname, prop)
    if name:
        setter = frappe.get_doc("Property Setter", name)
        if setter.value != str(value) or setter.property_type != fieldtype:
            setter.value = str(value)
            setter.property_type = fieldtype
            setter.flags.validate_fields_for_doctype = True
            setter.save(ignore_permissions=True)
    elif explicit or target.get(prop) != value:
        make_property_setter(
            meta.name, fieldname, prop, value, fieldtype, for_doctype=not fieldname
        )


def enable_submitted_fields(meta, fieldnames):
    custom_fields = []
    for fieldname in fieldnames:
        field = meta.get_field(fieldname)
        if not field:
            continue
        if field.get("is_custom_field"):
            custom_fields.append(dict(fieldname=fieldname, allow_on_submit=1))
        else:
            set_property(meta, fieldname, "allow_on_submit", 1, "Check", explicit=True)

    if not custom_fields:
        return
    create_custom_fields({meta.name: custom_fields})
    for field in custom_fields:
        fieldname = field["fieldname"]
        name = get_property_setter_name(meta.name, fieldname, "allow_on_submit")
        if not name:
            continue
        setter = frappe.get_doc("Property Setter", name)
        if setter.is_system_generated and setter.value == "1":
            # Earlier releases stored this override on the Property Setter instead.
            frappe.delete_doc("Property Setter", name, ignore_permissions=True)
        elif setter.value != "1":
            set_property(meta, fieldname, "allow_on_submit", 1, "Check")


def configure_batch_fields():
    for doctype, child in DOCTYPE_ITEMS.items():
        meta = frappe.get_meta(child)
        fields = [
            dict(
                fieldname=fieldname, label=label, fieldtype="Date",
                insert_after=insert_after, read_only=1,
            )
            for fieldname, label, insert_after in (
                ("batch_expiry_date", "Batch Expiry Date", "batch_no"),
                ("batch_manufacturing_date", "Batch Manufacturing Date", "batch_expiry_date"),
            )
            if not meta.has_field(fieldname)
        ]
        fields.append(dict(
            fieldname="custom_posted_batches", label="Batch Details", fieldtype="HTML",
            insert_after="item_code", depends_on=BATCH_DETAILS_VISIBLE,
        ))
        fields.append(dict(
            fieldname=INFORMATIONAL_BATCH, label="Informational Batch Reference",
            fieldtype="Link", options="Batch", insert_after="custom_posted_batches",
            hidden=1, print_hide=1, no_copy=1, allow_on_submit=1,
        ))
        create_custom_fields({child: fields})
        meta = frappe.get_meta(child)
        enable_submitted_fields(meta, BATCH_DATES)

        if doctype == "Sales Invoice":
            enable_submitted_fields(meta, ("batch_no",))
        else:
            set_property(meta, "batch_no", "allow_on_submit", 0, "Check")
        draft_batch_condition = "doc.use_serial_batch_fields === 1" if doctype == "Delivery Note" else "true"
        submitted_batch_condition = "parent?.__onload?.devp_informational_batch_fields?.[doc.name] === 'batch_no'"
        set_property(
            meta, "batch_no", "depends_on",
            f"eval:doc.docstatus === 1 ? ({submitted_batch_condition}) : ({draft_batch_condition})",
            "Data",
        )
        for fieldname in BATCH_DATES:
            set_property(meta, fieldname, "depends_on", f"eval:!({LOCKED_BATCH})", "Data")


def install():
    fields = {}
    for doctype, child in DOCTYPE_ITEMS.items():
        parent_meta = frappe.get_meta(doctype)
        fields[doctype] = [
            dict(
                fieldname="custom_internal_transport_details", label="Internal Transport Details",
                fieldtype="Small Text", insert_after="transporter_info", no_copy=1, print_hide=1,
                depends_on=f"eval:{GOVERNMENT_TRANSPORT}", allow_on_submit=1,
                description="Record local transporter, receipt number and date, vehicle, mode or driver details here. This field is for internal records.",
            ),
        ]
        if not parent_meta.has_field("transporter_info"):
            fields[doctype].pop()
        if parent_meta.has_field("custom_terms_revision_reason"):
            # Keep the historical values available in Version history.
            fields[doctype].append(dict(fieldname="custom_terms_revision_reason", hidden=1, allow_on_submit=0))

    create_custom_fields(fields)

    for doctype, child in DOCTYPE_ITEMS.items():
        meta = frappe.get_meta(doctype)
        set_property(meta, None, "track_changes", 1, "Check")
        enable_submitted_fields(meta, ("tc_name", "terms", "description_sales_invoice", *TRANSPORT_FIELDS))
        meta = frappe.get_meta(doctype)

        for fieldname in TRANSPORT_FIELDS:
            field = meta.get_field(fieldname)
            if not field:
                continue
            existing = field.read_only_depends_on
            if existing and not existing.startswith("eval:"):
                condition = f"doc[{existing!r}] || ({GOVERNMENT_TRANSPORT})"
            elif existing and GOVERNMENT_TRANSPORT not in existing:
                condition = f"({existing[5:]}) || ({GOVERNMENT_TRANSPORT})"
            else:
                condition = existing[5:] if existing else GOVERNMENT_TRANSPORT
            set_property(meta, fieldname, "read_only_depends_on", "eval:" + condition, "Data")

        meta = frappe.get_meta(child)
        enable_submitted_fields(meta, ("description", "description_sales_invoice", "customer_description"))

    configure_batch_fields()

    invoice = frappe.get_meta("Sales Invoice")
    enable_submitted_fields(invoice, ("payment_terms_template", "payment_schedule", "due_date"))
    set_property(invoice, "payment_terms_template", "read_only_depends_on",
                 "eval:doc.docstatus === 1 && doc.__onload?.devp_schedule_blocker !== ''", "Data")
    set_property(invoice, "payment_schedule", "read_only_depends_on", "eval:doc.docstatus === 1", "Data")
    set_property(invoice, "due_date", "read_only_depends_on", "eval:doc.docstatus === 1", "Data")
    schedule = frappe.get_meta("Payment Schedule")
    enable_submitted_fields(schedule, SCHEDULE_FIELDS)
    for field in SCHEDULE_FIELDS:
        set_property(schedule, field, "read_only_depends_on", "eval:parent?.docstatus === 1", "Data")

    # The existing Desk script restores draft descriptions after ERPNext's item mapping.
    # Submitted values must stay exactly as returned by the server.
    name = "Description edit"
    if frappe.db.exists("Client Script", {"name": name, "dt": "Sales Invoice"}):
        script = frappe.get_doc("Client Script", name)
        guard = "        if (frm.doc.docstatus !== 0) return;"
        original = script.script
        for handler in ("before_save", "after_save"):
            signature = f"    {handler}(frm) {{"
            if f"{signature}\n{guard}" not in script.script:
                script.script = script.script.replace(signature, f"{signature}\n{guard}", 1)
        if script.script != original:
            script.save(ignore_permissions=True)
