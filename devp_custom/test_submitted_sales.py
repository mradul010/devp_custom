import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_delivery_note
from erpnext.accounts.utils import get_fiscal_year
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.serial_batch_bundle import SerialBatchCreation
from frappe.desk.form.load import run_onload
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase, set_user
from frappe.utils import add_days, getdate, today

from devp_custom.submitted_sales import INFORMATIONAL_BATCH, get_batch_dates
from devp_custom.submitted_payment_schedule import preview_payment_schedule


class TestSubmittedSales(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stock_settings = frappe.get_single("Stock Settings")
        stock_settings.enable_serial_and_batch_no_for_item = 1
        stock_settings.save()
        cls.company = frappe.get_doc(
            doctype="Company", company_name=f"Submitted Sales {frappe.generate_hash(length=6)}",
            abbr=frappe.generate_hash(length=4), country="India", default_currency="INR",
        ).insert()
        cls.warehouse = cls.company.reload().default_warehouse
        cls.customer = frappe.get_doc(
            doctype="Customer", customer_name=f"Submitted Sales {frappe.generate_hash(length=6)}",
            customer_type="Company",
        ).insert()
        cls.price_list = frappe.get_doc(
            doctype="Price List", price_list_name=f"Submitted Sales {frappe.generate_hash(length=6)}",
            currency="INR", selling=1, enabled=1,
        ).insert().name
        if not get_fiscal_year(today(), company=cls.company.name, raise_on_missing=False):
            year = getdate().year
            frappe.get_doc(
                doctype="Fiscal Year", year=f"Submitted Sales {year}",
                year_start_date=f"{year}-01-01", year_end_date=f"{year}-12-31",
                companies=[{"company": cls.company.name}],
            ).insert()

    def make_item(self, batched=False, *, item_code=None, stock=None):
        return frappe.get_doc(
            doctype="Item", item_code=item_code or frappe.generate_hash(length=10), item_name="Submitted Sales Item",
            item_group="All Item Groups", stock_uom="Nos",
            is_stock_item=int(batched if stock is None else stock), has_batch_no=int(batched), gst_hsn_code="84713010",
        ).insert().name

    def make_voucher(self, doctype, item, batches=None, qty=1, rate=100, update_stock=0):
        voucher = frappe.get_doc(
            doctype=doctype, company=self.company.name, customer=self.customer.name, currency="INR",
            selling_price_list=self.price_list, price_list_currency="INR", plc_conversion_rate=1,
        )
        if doctype == "Sales Invoice":
            voucher.update_stock = update_stock
        bundle = None
        if batches:
            bundle = SerialBatchCreation({
                "item_code": item, "warehouse": self.warehouse, "voucher_type": doctype,
                "qty": qty, "batches": batches, "type_of_transaction": "Outward",
                "company": self.company.name, "do_not_submit": True,
            }).make_serial_and_batch_bundle().name
        voucher.append("items", {
            "item_code": item, "warehouse": self.warehouse, "qty": qty, "rate": rate,
            "serial_and_batch_bundle": bundle,
        })
        return voucher

    def make_batch(self, item):
        return frappe.get_doc(
            doctype="Batch",
            batch_id=frappe.generate_hash(length=10),
            item=item,
            manufacturing_date=add_days(today(), -10),
            expiry_date=add_days(today(), 90),
        ).insert()

    def make_carrier(self):
        return frappe.get_doc(
            doctype="Supplier", supplier_name=f"Submitted Carrier {frappe.generate_hash(length=6)}",
            supplier_type="Company", supplier_group="All Supplier Groups", is_transporter=1,
        ).insert()

    def make_operator(self, role):
        email = f"submitted-sales-{frappe.generate_hash(length=8)}@example.test"
        return frappe.get_doc(
            doctype="User", email=email, first_name="Submitted Sales Operator",
            user_type="System User", send_welcome_email=0, roles=[{"role": role}],
        ).insert().name

    def ledger(self, doc):
        return {
            dt: frappe.get_all(
                dt, filters={"voucher_type": doc.doctype, "voucher_no": doc.name},
                fields=["name", "modified"], order_by="name",
            )
            for dt in ("Stock Ledger Entry", "GL Entry", "Payment Ledger Entry")
        }

    def update_from_desk(self, doc):
        frappe.response.docs = []
        savedocs(doc.as_json(), "Update")
        self.assertEqual(frappe.response.docs[0]["docstatus"], 1)
        self.assertEqual(frappe.response.docs[0]["lr_no"], doc.lr_no)
        doc.reload()

    def test_property_setters_and_custom_field_metadata(self):
        for parent in ("Sales Invoice", "Delivery Note"):
            for field in ("tc_name", "terms"):
                setter = frappe.get_doc("Property Setter", f"{parent}-{field}-allow_on_submit")
                self.assertEqual((setter.doctype_or_field, setter.property_type, setter.value),
                                 ("DocField", "Check", "1"))
            child = f"{parent} Item"
            child_meta = frappe.get_meta(child)
            self.assertTrue(child_meta.get_field("description").allow_on_submit)
            self.assertFalse(frappe.get_meta(parent).get_field("items").allow_on_submit)
            fieldnames = [field.fieldname for field in child_meta.fields]
            self.assertLess(fieldnames.index("custom_posted_batches"), fieldnames.index("description"))
            self.assertIn("devp_informational_batch_rows", child_meta.get_field("custom_posted_batches").depends_on)
            for fieldname in ("batch_manufacturing_date", "batch_expiry_date"):
                field = frappe.get_meta(child).get_field(fieldname)
                self.assertTrue(field.read_only)
                self.assertTrue(field.allow_on_submit)
                self.assertTrue(frappe.db.get_value(
                    "Custom Field", {"dt": child, "fieldname": fieldname}, "allow_on_submit"
                ))
        self.assertTrue(frappe.get_meta("Sales Invoice Item").get_field("batch_no").allow_on_submit)
        self.assertFalse(frappe.get_meta("Delivery Note Item").get_field("batch_no").allow_on_submit)
        for fieldname in ("description_sales_invoice", "transporter", "lr_no", "lr_date"):
            self.assertTrue(frappe.db.get_value(
                "Custom Field", {"dt": "Sales Invoice", "fieldname": fieldname}, "allow_on_submit"
            ))

    def test_informational_sales_invoice_batch_and_descriptions(self):
        item = self.make_item(batched=True)
        batch = self.make_batch(item)
        replacement = self.make_batch(item)
        invoice = self.make_voucher("Sales Invoice", item)
        second = invoice.items[0].as_dict()
        second.pop("name", None)
        invoice.append("items", second)
        invoice.items[0].batch_no = batch.name
        invoice.insert()
        self.assertEqual(getdate(invoice.items[0].batch_expiry_date), getdate(batch.expiry_date))
        self.assertEqual(getdate(get_batch_dates(batch.name)["manufacturing_date"]), getdate(batch.manufacturing_date))
        invoice.submit()
        invoice.reload()
        run_onload(invoice)
        self.assertIn(invoice.items[0].name, invoice.get_onload("devp_informational_batch_rows"))
        before = self.ledger(invoice)
        quantity, rate, total, outstanding = (
            invoice.items[0].qty, invoice.items[0].rate, invoice.grand_total, invoice.outstanding_amount
        )
        other_description = invoice.items[1].description

        invoice.items[0].batch_no = replacement.name
        invoice.items[0].batch_expiry_date = "1900-01-01"
        invoice.items[0].description = "<p>Edited <strong>description</strong></p>"
        invoice.items[0].customer_description = "Updated customer description"
        invoice.description_sales_invoice = "Header description"
        invoice.lr_no = "LR-TEST-123"
        invoice.lr_date = today()
        invoice.po_no = "PO-TEST-123"
        invoice.save(ignore_version=False)
        invoice.reload()

        self.assertLess(invoice.grand_total, 50_000)
        self.assertFalse(invoice.ewaybill)
        self.assertEqual(invoice.items[0].batch_no, replacement.name)
        self.assertEqual(getdate(invoice.items[0].batch_expiry_date), getdate(replacement.expiry_date))
        self.assertEqual(invoice.items[0].description, "<p>Edited <strong>description</strong></p>")
        self.assertEqual(invoice.items[1].description, other_description)
        self.assertEqual(invoice.items[0].customer_description, "Updated customer description")
        self.assertFalse(invoice.items[1].customer_description)
        self.assertEqual(invoice.description_sales_invoice, "Header description")
        self.assertEqual(invoice.lr_no, "LR-TEST-123")
        self.assertEqual(invoice.po_no, "PO-TEST-123")
        terms = frappe.get_doc(
            doctype="Terms and Conditions", title=frappe.generate_hash(), selling=1,
            terms="<p>Terms from template</p>",
        ).insert()
        invoice.tc_name = terms.name
        carrier = self.make_carrier()
        invoice.transporter = carrier.name
        invoice.lr_no = "LR-DESK-123"
        self.update_from_desk(invoice)
        self.assertEqual(invoice.transporter, carrier.name)
        self.assertEqual(invoice.transporter_name, carrier.supplier_name)
        self.assertEqual(invoice.lr_no, "LR-DESK-123")
        self.assertEqual(invoice.description_sales_invoice, "Header description")
        self.assertEqual(invoice.terms, terms.terms)
        invoice.lr_no = "LR-ACCOUNTS-USER"
        invoice.po_no = "PO-ACCOUNTS-USER"
        operator = self.make_operator("Accounts User")
        with set_user(operator):
            self.assertFalse(frappe.has_permission("Batch", "read", doc=replacement.name))
            self.assertTrue(frappe.has_permission("Batch", "select", doc=replacement.name))
            self.assertEqual(getdate(get_batch_dates(replacement.name)["expiry_date"]),
                             getdate(replacement.expiry_date))
            self.update_from_desk(invoice)
        self.assertEqual(invoice.lr_no, "LR-ACCOUNTS-USER")
        self.assertEqual(invoice.po_no, "PO-ACCOUNTS-USER")
        self.assertEqual((invoice.items[0].qty, invoice.items[0].rate, invoice.grand_total,
                          invoice.outstanding_amount), (quantity, rate, total, outstanding))
        self.assertEqual(self.ledger(invoice), before)
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": invoice.doctype, "docname": invoice.name}))

        wrong_item = self.make_item(batched=True)
        invoice.items[0].batch_no = self.make_batch(wrong_item).name
        with self.assertRaisesRegex(frappe.ValidationError, "enabled batch"):
            invoice.save()

        invoice.reload()
        invoice.items[0].batch_no = None
        invoice.save()
        invoice.reload()
        self.assertFalse(invoice.items[0].batch_expiry_date)
        self.assertFalse(invoice.items[0].batch_manufacturing_date)
        invoice.items[0].qty += 1
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            invoice.save()

        invoice.reload()
        invoice.items.pop()
        with self.assertRaisesRegex(frappe.ValidationError, "item rows cannot be"):
            invoice.save()

    def test_dsg1106_non_batched_item_can_save_informational_reference(self):
        item = "DISPOSABLE PLASTIC APRON"
        if not frappe.db.exists("Item", item):
            self.make_item(item_code=item, stock=True)
        self.assertEqual(frappe.db.get_value("Item", item, ["is_stock_item", "has_batch_no"]), (1, 0))
        batch = self.make_batch(self.make_item(batched=True))
        invoice = self.make_voucher("Sales Invoice", item, rate=23, update_stock=0)
        invoice.items[0].use_serial_batch_fields = 1
        invoice.insert().submit().reload()
        row = invoice.items[0]
        ledger = self.ledger(invoice)
        run_onload(invoice)
        self.assertEqual(invoice.get_onload("devp_batch_allocations"), {})
        self.assertEqual(invoice.get_onload("devp_informational_batch_fields"), {row.name: INFORMATIONAL_BATCH})
        self.assertFalse(row.batch_no)
        self.assertFalse(row.serial_and_batch_bundle)
        operator = self.make_operator("Accounts User")
        with set_user(operator):
            dates = get_batch_dates(batch.name)
            row.set(INFORMATIONAL_BATCH, batch.name)
            self.update_from_desk(invoice)

        row = invoice.items[0]
        self.assertEqual(row.get(INFORMATIONAL_BATCH), batch.name)
        self.assertEqual(getdate(row.batch_manufacturing_date), dates["manufacturing_date"])
        self.assertEqual(getdate(row.batch_expiry_date), dates["expiry_date"])
        self.assertFalse(row.batch_no)
        self.assertFalse(row.serial_and_batch_bundle)
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(invoice.grand_total, 23)
        self.assertEqual(self.ledger(invoice), ledger)
        self.assertFalse(ledger["Stock Ledger Entry"])

        run_onload(invoice)
        details = invoice.get_onload("devp_informational_batch_details")[row.name]
        self.assertEqual(details, [{
            "fieldname": INFORMATIONAL_BATCH, "batch_no": batch.name, **dates,
        }])
        invoice.run_method("before_print", frappe.get_single("Print Settings"))
        invoice.run_method("before_print", frappe.get_single("Print Settings"))
        self.assertEqual(row.batch_no, f"Informational Batch Reference ({batch.name})")
        self.assertEqual(getdate(row.batch_manufacturing_date), dates["manufacturing_date"])
        self.assertEqual(getdate(row.batch_expiry_date), dates["expiry_date"])
        invoice.reload()
        self.assertFalse(invoice.items[0].batch_no)

        delivery = make_delivery_note(invoice.name)
        self.assertFalse(delivery.items[0].get(INFORMATIONAL_BATCH))
        self.assertFalse(delivery.items[0].batch_no)
        invoice.items[0].batch_no = batch.name
        with self.assertRaisesRegex(frappe.ValidationError, "informational batch editor"):
            invoice.save()

    def test_nonstock_delivery_note_can_save_informational_reference(self):
        item = self.make_item()
        batch = self.make_batch(self.make_item(batched=True))
        note = self.make_voucher("Delivery Note", item)
        note.insert().submit().reload()
        run_onload(note)
        row = note.items[0]
        self.assertEqual(note.get_onload("devp_informational_batch_fields"), {row.name: INFORMATIONAL_BATCH})
        row.set(INFORMATIONAL_BATCH, batch.name)
        self.update_from_desk(note)
        self.assertEqual(note.items[0].get(INFORMATIONAL_BATCH), batch.name)
        self.assertFalse(note.items[0].batch_no)
        self.assertFalse(self.ledger(note)["Stock Ledger Entry"])
        run_onload(note)
        saved = note.get_onload("devp_informational_batch_details")[row.name]
        self.assertEqual(saved[0]["batch_no"], batch.name)
        self.assertEqual(saved[0]["manufacturing_date"], getdate(batch.manufacturing_date))
        self.assertEqual(saved[0]["expiry_date"], getdate(batch.expiry_date))
        note.run_method("before_print", frappe.get_single("Print Settings"))
        self.assertEqual(note.items[0].batch_no, f"Informational Batch Reference ({batch.name})")
        note.reload()
        self.assertFalse(note.items[0].batch_no)

    def test_informational_details_stay_bound_to_invoice_and_item_row(self):
        item = self.make_item()
        batch_item = self.make_item(batched=True)
        legacy, first, second, unrelated = [self.make_batch(batch_item) for _ in range(4)]
        invoice = self.make_voucher("Sales Invoice", item)
        invoice.items[0].batch_no = legacy.name
        invoice.append("items", {"item_code": item, "qty": 1, "rate": 100, "description": "Second row"})
        invoice.insert().submit().reload()
        other_invoice = self.make_voucher("Sales Invoice", item)
        other_invoice.insert().submit().reload()
        other_invoice.items[0].set(INFORMATIONAL_BATCH, unrelated.name)
        self.update_from_desk(other_invoice)
        invoice.items[0].set(INFORMATIONAL_BATCH, first.name)
        invoice.items[1].set(INFORMATIONAL_BATCH, second.name)
        self.update_from_desk(invoice)

        run_onload(invoice)
        details = invoice.get_onload("devp_informational_batch_details")
        self.assertEqual({
            row: [batch["batch_no"] for batch in references] for row, references in details.items()
        }, {
            invoice.items[0].name: [first.name, legacy.name],
            invoice.items[1].name: [second.name],
        })
        self.assertEqual(details[invoice.items[0].name][1]["expiry_date"], getdate(legacy.expiry_date))

    def test_stock_vouchers_keep_the_posted_allocation(self):
        item = self.make_item(batched=True)
        first = self.make_batch(item)
        second = self.make_batch(item)
        second.manufacturing_date = add_days(today(), -3)
        second.expiry_date = add_days(today(), 60)
        second.save()
        carrier = self.make_carrier()
        for batch in (first, second):
            make_stock_entry(
                item_code=item, qty=10, to_warehouse=self.warehouse,
                rate=25, batch_no=batch.name, company=self.company.name,
            )

        for doctype, batches, qty in (
            ("Delivery Note", {first.name: -1, second.name: -1}, 2),
            ("Sales Invoice", {first.name: -1}, 1),
        ):
            doc = self.make_voucher(doctype, item, batches=batches, qty=qty, update_stock=1)
            doc.insert()
            doc.submit()
            doc.reload()
            with self.subTest(doctype=doc.doctype):
                before = self.ledger(doc)
                self.assertTrue(before["Stock Ledger Entry"])
                run_onload(doc)
                self.assertFalse(doc.get_onload("devp_informational_batch_rows"))
                allocation = doc.get_onload("devp_batch_allocations")[doc.items[0].name]
                expected = [first.name, second.name] if doc.doctype == "Delivery Note" else [first.name]
                self.assertCountEqual([entry["batch_no"] for entry in allocation["batches"]], expected)
                doc.items[0].batch_no = second.name
                with self.assertRaisesRegex(frappe.ValidationError, "linked to stock"):
                    doc.save()
                doc.reload()
                doc.items[0].set(INFORMATIONAL_BATCH, second.name)
                with self.assertRaisesRegex(frappe.ValidationError, "linked to stock"):
                    doc.save()

                doc.reload()
                doc.items[0].description = "<p>Updated stock voucher description</p>"
                doc.terms = "<p>Updated terms</p>"
                doc.lr_no = "LR-STOCK"
                doc.save(ignore_version=False)
                doc.reload()
                self.assertIn("Updated stock voucher description", doc.items[0].description)
                self.assertIn("Updated terms", doc.terms)
                self.assertEqual(doc.lr_no, "LR-STOCK")
                self.assertEqual(self.ledger(doc), before)
                version = frappe.db.get_value(
                    "Version", {"ref_doctype": doc.doctype, "docname": doc.name}, "data", order_by="creation desc"
                )
                self.assertTrue(any(
                    change[0] == "terms" and change[2] == doc.terms
                    for change in frappe.parse_json(version)["changed"]
                ))
                doc.items[0].description = "<p>Updated stock voucher in Desk</p>"
                doc.transporter = carrier.name
                doc.lr_no = "LR-STOCK-DESK"
                doc.lr_date = today()
                if doctype == "Delivery Note":
                    operator = self.make_operator("Stock User")
                    with set_user(operator):
                        self.update_from_desk(doc)
                else:
                    self.update_from_desk(doc)
                self.assertEqual(doc.lr_no, "LR-STOCK-DESK")
                self.assertEqual(doc.transporter, carrier.name)
                self.assertEqual(doc.transporter_name, carrier.supplier_name)
                self.assertEqual(getdate(doc.lr_date), getdate())
                self.assertEqual(self.ledger(doc), before)
                output = frappe.get_print(doc.doctype, doc.name, "Standard", no_letterhead=1)
                self.assertIn("Updated stock voucher in Desk", output)
                self.assertIn("Updated terms", output)

                doc.cancel()
                amended = self.make_voucher(doctype, item, batches={second.name: -1}, update_stock=1)
                amended.amended_from = doc.name
                amended.insert()
                amended.submit()
                amended.reload()
                self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "docstatus"), 2)
                self.assertEqual(getdate(amended.items[0].batch_manufacturing_date), getdate(second.manufacturing_date))
                self.assertEqual(getdate(amended.items[0].batch_expiry_date), getdate(second.expiry_date))
                run_onload(amended)
                posted = amended.get_onload("devp_batch_allocations")[amended.items[0].name]["batches"]
                self.assertEqual([entry["batch_no"] for entry in posted], [second.name])

    def test_later_delivery_controls_invoice_batch_display(self):
        item = self.make_item(batched=True)
        reference = self.make_batch(item)
        posted = self.make_batch(item)
        make_stock_entry(
            item_code=item, qty=5, to_warehouse=self.warehouse, rate=25,
            batch_no=posted.name, company=self.company.name,
        )
        invoice = self.make_voucher("Sales Invoice", item)
        invoice.items[0].batch_no = reference.name
        invoice.insert()
        invoice.submit()

        note = self.make_voucher("Delivery Note", item, batches={posted.name: -1})
        note.items[0].against_sales_invoice = invoice.name
        note.items[0].si_detail = invoice.items[0].name
        note.insert()
        note.submit()

        invoice.reload()
        run_onload(invoice)
        allocation = invoice.get_onload("devp_batch_allocations")[invoice.items[0].name]
        self.assertEqual(allocation["batches"][0]["batch_no"], posted.name)
        self.assertEqual(allocation["vouchers"], [{"doctype": "Delivery Note", "name": note.name}])
        invoice.items[0].batch_no = None
        with self.assertRaisesRegex(frappe.ValidationError, "linked to stock"):
            invoice.save()
        invoice.reload()
        invoice.run_method("before_print", frappe.get_single("Print Settings"))
        self.assertEqual(invoice.items[0].batch_no, posted.name)
        invoice.reload()
        self.assertEqual(invoice.items[0].batch_no, reference.name)

    def test_government_transport_fields_and_internal_details(self):
        carrier = self.make_carrier()
        invoice = self.make_voucher("Sales Invoice", self.make_item(), rate=60_000)
        invoice.transporter = carrier.name
        invoice.lr_date = today()
        invoice.insert()
        invoice.submit()
        invoice.db_set("ewaybill", "123456789012")
        # A Supplier master change must leave the reported transporter name intact.
        reported_name = invoice.transporter_name
        self.assertTrue(reported_name)
        carrier.db_set("supplier_name", "Renamed Carrier")
        invoice.reload()
        invoice.lr_no = "ATTEMPT"
        with self.assertRaises(frappe.ValidationError):
            invoice.save()
        invoice.reload()
        invoice.lr_date = None
        with self.assertRaises(frappe.ValidationError):
            invoice.save()
        invoice.reload()
        invoice.custom_internal_transport_details = "Carrier was advised of receipt LR-815"
        invoice.save()
        invoice.reload()
        self.assertEqual(invoice.ewaybill, "123456789012")
        self.assertFalse(invoice.lr_no)
        self.assertEqual(invoice.transporter_name, reported_name)
        self.assertIn("LR-815", invoice.custom_internal_transport_details)

        with set_user("Guest"):
            invoice.custom_internal_transport_details = "Unauthorized change"
            with self.assertRaises(frappe.PermissionError):
                invoice.save()

    def make_template(self, days=(10, 30)):
        return frappe.get_doc(
            doctype="Payment Terms Template",
            template_name=f"Submitted schedule {frappe.generate_hash(length=8)}",
            terms=[
                {
                    "invoice_portion": 40 if idx == 0 else 60,
                    "due_date_based_on": "Day(s) after invoice date",
                    "credit_days": days_due,
                }
                for idx, days_due in enumerate(days)
            ],
        ).insert()

    def test_unpaid_invoice_template_and_schedule_update(self):
        item = self.make_item(batched=True)
        batch = self.make_batch(item)
        make_stock_entry(
            item_code=item, qty=5, to_warehouse=self.warehouse, rate=25,
            batch_no=batch.name, company=self.company.name,
        )
        doc = self.make_voucher(
            "Sales Invoice", item, batches={batch.name: -1}, rate=60_001, update_stock=1
        )
        doc.due_date = add_days(today(), 30)
        doc.insert().submit().reload()
        ledger = self.ledger(doc)
        self.assertTrue(ledger["Stock Ledger Entry"])
        totals = (doc.grand_total, doc.outstanding_amount, doc.due_date)
        template = self.make_template()
        operator = self.make_operator("Accounts User")
        with set_user(operator):
            preview = preview_payment_schedule(doc.name, template.name)
            self.assertFalse(preview["requires_amendment"])
            self.assertEqual([row["invoice_portion"] for row in preview["rows"]], [40, 60])
            self.assertEqual([getdate(row["due_date"]) for row in preview["rows"]],
                             [getdate(add_days(doc.posting_date, d)) for d in (10, 30)])
            self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "payment_terms_template"), None)
            doc.payment_terms_template = template.name
            self.update_from_desk(doc)
        self.assertEqual(doc.payment_terms_template, template.name)
        self.assertEqual(len(doc.payment_schedule), 2)
        self.assertAlmostEqual(sum(row.payment_amount for row in doc.payment_schedule), doc.grand_total)
        self.assertAlmostEqual(sum(row.outstanding for row in doc.payment_schedule), doc.outstanding_amount)
        names = [row.name for row in doc.payment_schedule]

        doc.payment_schedule[0].due_date = add_days(doc.posting_date, 15)
        doc.payment_schedule[0].invoice_portion = 30
        doc.payment_schedule[1].invoice_portion = 70
        preview = preview_payment_schedule(doc.name, template.name, frappe.as_json([
            {"name": row.name, "due_date": row.due_date, "invoice_portion": row.invoice_portion}
            for row in doc.payment_schedule
        ]))
        self.assertAlmostEqual(preview["rows"][0]["payment_amount"], 18_000.30)
        self.update_from_desk(doc)
        self.assertEqual([row.name for row in doc.payment_schedule], names)
        self.assertEqual(getdate(doc.payment_schedule[0].due_date), getdate(add_days(doc.posting_date, 15)))
        self.assertAlmostEqual(doc.payment_schedule[0].payment_amount, 18_000.30)
        self.assertEqual((doc.grand_total, doc.outstanding_amount, doc.due_date), totals)
        self.assertEqual(self.ledger(doc), ledger)
        incompatible = self.make_template(days=(10, 45))
        changed_date_preview = preview_payment_schedule(doc.name, incompatible.name)
        self.assertTrue(changed_date_preview["requires_amendment"])
        self.assertEqual(getdate(changed_date_preview["due_date"]), getdate(add_days(doc.posting_date, 45)))
        doc.payment_schedule[0].invoice_portion = 20
        with self.assertRaisesRegex(frappe.ValidationError, "add up to 100"):
            self.update_from_desk(doc)

    def test_changed_posted_due_date_uses_standard_amendment(self):
        item = self.make_item()
        doc = self.make_voucher("Sales Invoice", item, rate=250)
        doc.due_date = add_days(today(), 20)
        doc.insert().submit().reload()
        original_due_date = getdate(doc.due_date)
        original_ledger = self.ledger(doc)
        template = self.make_template(days=(10, 40))
        preview = preview_payment_schedule(doc.name, template.name)
        self.assertTrue(preview["requires_amendment"])
        self.assertEqual(getdate(preview["due_date"]), getdate(add_days(doc.posting_date, 40)))
        doc.payment_terms_template = template.name
        doc.due_date = preview["due_date"]
        with self.assertRaisesRegex(frappe.ValidationError, "Prepare Due Date Amendment"):
            self.update_from_desk(doc)
        doc.reload()
        self.assertEqual(getdate(doc.due_date), original_due_date)
        self.assertEqual(self.ledger(doc), original_ledger)

        doc.cancel()
        amended = self.make_voucher("Sales Invoice", item, rate=250)
        amended.amended_from = doc.name
        amended.due_date = preview["due_date"]
        amended.payment_terms_template = template.name
        amended.set("payment_schedule", preview["rows"])
        amended.insert().submit().reload()
        self.assertEqual(getdate(amended.due_date), getdate(preview["due_date"]))
        self.assertEqual(max(getdate(row.due_date) for row in amended.payment_schedule), getdate(amended.due_date))
        self.assertEqual(amended.grand_total, doc.grand_total)
        for ledger_type in ("GL Entry", "Payment Ledger Entry"):
            self.assertTrue(frappe.db.exists(ledger_type, {
                "voucher_type": "Sales Invoice", "voucher_no": amended.name,
                "account": amended.debit_to, "due_date": amended.due_date,
            }))
            self.assertTrue(frappe.db.exists(ledger_type, {
                "voucher_type": "Sales Invoice", "voucher_no": doc.name,
                "account": doc.debit_to, "due_date": original_due_date,
            }))

    def test_invoice_with_real_partial_payment_blocks_schedule_only(self):
        doc = self.make_voucher("Sales Invoice", self.make_item(), rate=200)
        doc.due_date = add_days(today(), 30)
        doc.insert().submit().reload()
        payment = get_payment_entry("Sales Invoice", doc.name, party_amount=50,
                                    bank_account=self.company.default_cash_account)
        payment.insert()
        template = self.make_template()
        with self.assertRaisesRegex(frappe.ValidationError, "references this invoice"):
            preview_payment_schedule(doc.name, template.name)
        payment.submit()
        doc.reload()
        self.assertEqual(doc.outstanding_amount, 150)
        with self.assertRaisesRegex(frappe.ValidationError, "payment, advance"):
            preview_payment_schedule(doc.name, template.name)
        doc.payment_terms_template = template.name
        with self.assertRaisesRegex(frappe.ValidationError, "payment, advance"):
            self.update_from_desk(doc)
        doc.reload()
        self.assertFalse(doc.payment_terms_template)
        doc.terms = "<p>Payment received and acknowledged.</p>"
        self.update_from_desk(doc)
        self.assertIn("Payment received and acknowledged", doc.terms)
        self.assertEqual(doc.outstanding_amount, 150)

    def test_shared_payment_schedule_does_not_unlock_sales_order(self):
        order = self.make_voucher("Sales Order", self.make_item())
        order.delivery_date = add_days(today(), 10)
        order.items[0].delivery_date = order.delivery_date
        order.insert().submit().reload()
        order.payment_schedule[0].invoice_portion = 90
        with self.assertRaisesRegex(frappe.UpdateAfterSubmitError, "eligible Sales Invoices"):
            order.save()
        order.reload()
        self.assertEqual(order.payment_schedule[0].invoice_portion, 100)
