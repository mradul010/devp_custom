# devparvsurgico/patches/add_drug_license_fields.py

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    fields = {
        "Customer": [
            {
                "fieldname": "drug_license_number",
                "label": "Drug License Number",
                "fieldtype": "Data",
                "insert_after": "customer_group",   # change to whichever field you prefer
                "allow_on_submit": 0,
                "hidden": 0,
                "read_only": 0,
                "reqd": 0,
                "in_list_view": 1,         # show in list view if useful
                "print_hide": 0
            }
        ]
    }

    create_custom_fields(fields, update=True)
    frappe.db.commit()
