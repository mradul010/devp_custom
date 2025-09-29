# devp_custom/patches/add_batch_size_to_batch.py
import frappe

def execute():
    fieldname = "batch_size"
    doctype = "Batch"
    if not frappe.db.exists("Custom Field", f"{doctype}-{fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": doctype,
            "fieldname": fieldname,
            "label": "Batch Size",
            "fieldtype": "Float",
            "insert_after": "expiry_date",   # adjust position as you like
            "description": "Maximum quantity allowed for this batch",
            "reqd": 0
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.msgprint(f"Custom Field {doctype}.{fieldname} created.")
    else:
        frappe.msgprint(f"Custom Field {doctype}.{fieldname} already exists.")
