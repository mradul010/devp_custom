# -*- coding: utf-8 -*-
import frappe

def execute():
    targets = ["Sales Order Item", "Quotation Item", "Sales Invoice Item"]
    for dt in targets:
        if not frappe.db.exists("DocType", dt):
            print("Skipping", dt, "(doctype not present)")
            continue

        # 1) create customer_mapping (Link -> Item Customer Mapping)
        if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "customer_mapping"}):
            frappe.get_doc({
                "doctype":"Custom Field",
                "dt": dt,
                "fieldname": "customer_mapping",
                "label": "Customer Mapping",
                "fieldtype": "Link",
                "options": "Item Customer Mapping",
                "insert_after": "item_code",
                "in_list_view": 0
            }).insert(ignore_permissions=True)
            print("Created Custom Field:", dt + ".customer_mapping")
        else:
            print("Exists:", dt + ".customer_mapping")

        # 2) customer_item_name (Data)
        if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "customer_item_name"}):
            frappe.get_doc({
                "doctype":"Custom Field",
                "dt": dt,
                "fieldname": "customer_item_name",
                "label": "Customer Item Name",
                "fieldtype": "Data",
                "insert_after": "customer_mapping",
                "in_list_view": 1
            }).insert(ignore_permissions=True)
            print("Created Custom Field:", dt + ".customer_item_name")
        else:
            print("Exists:", dt + ".customer_item_name")

        # 3) customer_description (Text)
        if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "customer_description"}):
            frappe.get_doc({
                "doctype":"Custom Field",
                "dt": dt,
                "fieldname": "customer_description",
                "label": "Customer Description",
                "fieldtype": "Text",
                "insert_after": "customer_item_name",
                "in_list_view": 0
            }).insert(ignore_permissions=True)
            print("Created Custom Field:", dt + ".customer_description")
        else:
            print("Exists:", dt + ".customer_description")

    frappe.db.commit()
    print("create_transaction_custom_fields: done.")
