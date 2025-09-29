# devp_custom/patches/add_sales_invoice_description.py
import frappe

def execute():
    if not frappe.db.exists("Custom Field", "Sales Invoice-description"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Sales Invoice",
            "fieldname": "description_sales_invoice",
            "label": "Description Sales Invoice",
            "fieldtype": "Small Text",   # Small Text = multi-line text box
            "insert_after": "items",  # adjust as needed
            "reqd": 0
        }).insert()
        frappe.db.commit()
