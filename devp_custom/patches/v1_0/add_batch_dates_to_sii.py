import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def execute():
    # Define the two fields for Sales Invoice Item
    fields = [
        {
            "fieldname": "batch_expiry_date",
            "label": "Batch Expiry Date",
            "fieldtype": "Date",
            "insert_after": "batch_no",   # position near Batch No
            "read_only": 1,
            "print_hide": 0
        },
        {
            "fieldname": "batch_manufacturing_date",
            "label": "Batch Manufacturing Date",
            "fieldtype": "Date",
            "insert_after": "batch_expiry_date",
            "read_only": 1,
            "print_hide": 0
        }
    ]

    doctype = "Sales Invoice Item"

    for df in fields:
        # idempotent creation: create if missing, update basic props if exists
        if not frappe.db.exists("Custom Field", f"{doctype}-{df['fieldname']}"):
            create_custom_field(doctype, df, ignore_validate=True)
        else:
            cf = frappe.get_doc("Custom Field", f"{doctype}-{df['fieldname']}")
            # keep these in sync on re-run
            cf.label = df["label"]
            cf.fieldtype = df["fieldtype"]
            cf.insert_after = df["insert_after"]
            cf.read_only = df["read_only"]
            cf.print_hide = df["print_hide"]
            cf.save(ignore_permissions=True)
