# -*- coding: utf-8 -*-
import frappe

def execute():
    create_item_table_field()
    create_transaction_fields()
    frappe.db.commit()
    print("Patch complete: created item table field and transaction custom fields (if missing).")

def create_item_table_field():
    """
    Create the Table field on Item pointing to Item Customer Info
    """
    dt = "Item"
    fieldname = "customer_item_info"
    if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
        cf = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": dt,
            "fieldname": fieldname,
            "label": "Customer Item Info",
            "fieldtype": "Table",
            "options": "Item Customer Info",
            "insert_after": "description",
            "in_list_view": 0
        })
        cf.insert(ignore_permissions=True)
        print(f"Created Custom Field: {dt}.{fieldname}")
    else:
        print(f"Custom Field {dt}.{fieldname} already exists")

def create_transaction_fields():
    """
    Create 'customer_item_name' (Data) and 'customer_description' (Text)
    on transaction child doctypes (if present).
    """
    targets = [
        "Sales Order Item",
        "Quotation Item",
        "Sales Invoice Item"
    ]

    for child_doctype in targets:
        if not frappe.db.exists("DocType", child_doctype):
            print(f"Skipping {child_doctype}: DocType not present")
            continue

        # customer_item_name field
        field_name_name = "customer_item_name"
        if not frappe.db.exists("Custom Field", {"dt": child_doctype, "fieldname": field_name_name}):
            cf = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": child_doctype,
                "fieldname": field_name_name,
                "label": "Customer Item Name",
                "fieldtype": "Data",
                "insert_after": "item_name",
                "in_list_view": 1
            })
            cf.insert(ignore_permissions=True)
            print(f"Created Custom Field: {child_doctype}.{field_name_name}")
        else:
            print(f"Custom Field {child_doctype}.{field_name_name} already exists")

        # customer_description field
        field_name_desc = "customer_description"
        if not frappe.db.exists("Custom Field", {"dt": child_doctype, "fieldname": field_name_desc}):
            cf = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": child_doctype,
                "fieldname": field_name_desc,
                "label": "Customer Description",
                "fieldtype": "Text",
                "insert_after": field_name_name,
                "in_list_view": 0
            })
            cf.insert(ignore_permissions=True)
            print(f"Created Custom Field: {child_doctype}.{field_name_desc}")
        else:
            print(f"Custom Field {child_doctype}.{field_name_desc} already exists")
