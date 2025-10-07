# devp_custom/patches/add_batch_size_to_batch.py
import frappe
from frappe.utils import flt

def execute():
    # --- 1. Ensure Batch.batch_size exists ---
    doctype = "Batch"
    fieldname = "batch_size"

    if not frappe.db.exists("Custom Field", f"{doctype}-{fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": doctype,
            "fieldname": fieldname,
            "label": "Batch Size",
            "fieldtype": "Float",
            "insert_after": "expiry_date",   # adjust position as needed
            "description": "Maximum quantity allowed for this batch",
            "reqd": 0
        }).insert(ignore_permissions=True)
        frappe.msgprint(f"Custom Field {doctype}.{fieldname} created.")
    else:
        frappe.msgprint(f"Custom Field {doctype}.{fieldname} already exists.")

    # --- 2. Create Batch.available_batch_qty ---
    avail_field = "available_batch_qty"
    if not frappe.db.exists("Custom Field", f"{doctype}-{avail_field}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": doctype,
            "fieldname": avail_field,
            "label": "Available Batch Qty",
            "fieldtype": "Float",
            "insert_after": "batch_size",
            "description": "Remaining available quantity for this batch",
            "reqd": 0
        }).insert(ignore_permissions=True)
        frappe.msgprint(f"Custom Field {doctype}.{avail_field} created.")
    else:
        frappe.msgprint(f"Custom Field {doctype}.{avail_field} already exists.")

    # --- 3. Create Sales Invoice.allow_batch_exceed ---
    si_field = "allow_batch_exceed"
    si_doctype = "Sales Invoice"
    if not frappe.db.exists("Custom Field", f"{si_doctype}-{si_field}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": si_doctype,
            "fieldname": si_field,
            "label": "Allow Batch Exceed",
            "fieldtype": "Check",
            "insert_after": "title",  # place near top, hidden
            "default": "0",
            "read_only": 1,
            "hidden": 1,
            "no_copy": 1,
            "description": "Set automatically when Save Anyway is clicked in batch validation popup"
        }).insert(ignore_permissions=True)
        frappe.msgprint(f"Custom Field {si_doctype}.{si_field} created.")
    else:
        frappe.msgprint(f"Custom Field {si_doctype}.{si_field} already exists.")

    # --- 4. Initialize available_batch_qty = batch_size where empty ---
    frappe.reload_doc("custom", "doctype", "custom_field")

    if frappe.db.has_column("Batch", "batch_size") and frappe.db.has_column("Batch", "available_batch_qty"):
        batches = frappe.get_all("Batch", fields=["name", "batch_size", "available_batch_qty"])
        updated = 0

        for b in batches:
            if not b.batch_size:
                continue
            if b.available_batch_qty in (None, "", 0):
                frappe.db.set_value("Batch", b.name, "available_batch_qty", flt(b.batch_size), update_modified=False)
                updated += 1

        frappe.db.commit()
        frappe.msgprint(f"Initialized available_batch_qty for {updated} Batch record(s).")
    else:
        frappe.msgprint("Batch table missing one of the required columns (batch_size / available_batch_qty).")

    frappe.clear_cache()
