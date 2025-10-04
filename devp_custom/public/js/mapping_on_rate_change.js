// After user selects a price (your dialog sets `rate`), pull customer-mapping for that row.
// Works for Sales Order, Sales Invoice, and Quotation child rows.
// Uses your API: devp_custom.api.get_item_names_for_customer_batch

(function() {
  function normalize(v){ return (v || "").toString().trim(); }

  function fetch_and_apply_mapping_for_row(frm, row) {
    if (!row || !row.item_code || !frm.doc.customer) return;

    const item_code = normalize(row.item_code);
    const customer  = frm.doc.customer;

    frappe.call({
      method: "devp_custom.api.get_item_names_for_customer_batch",
      args: { item_codes: JSON.stringify([item_code]), customer: customer },
      callback: function(r) {
        if (!r || !r.message) return;
        const res = r.message[item_code] || {};
        // link to mapping doc
        frappe.model.set_value(row.doctype, row.name, "customer_mapping", res.mapping_name || "");
        // names/descriptions
        if (res.customer_item_name) {
          frappe.model.set_value(row.doctype, row.name, "customer_item_name", res.customer_item_name);
          frappe.model.set_value(row.doctype, row.name, "item_name", res.customer_item_name);
        } else {
          frappe.model.set_value(row.doctype, row.name, "customer_item_name", "");
        }
        if (res.customer_description) {
          frappe.model.set_value(row.doctype, row.name, "customer_description", res.customer_description);
          frappe.model.set_value(row.doctype, row.name, "description", res.customer_description);
        } else {
          frappe.model.set_value(row.doctype, row.name, "customer_description", "");
        }
        frm.refresh_field("items");
      },
      error: function(err) {
        console.error("mapping_on_rate_change: mapping fetch failed", err);
      }
    });
  }

  // Attach light listeners for all three child doctypes.
  // We listen on BOTH item_code and rate:
  // - item_code: in case user bypasses your dialog
  // - rate: fires right after your dialog applies the chosen price
  ["Sales Order Item", "Sales Invoice Item", "Quotation Item"].forEach(function(cdt) {
    frappe.ui.form.on(cdt, {
      item_code: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.item_code) return;
        fetch_and_apply_mapping_for_row(frm, row);
      },
      rate: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row) return;
        // Only fetch mapping when there is a rate and an item_code
        if (!row.item_code) return;
        fetch_and_apply_mapping_for_row(frm, row);
      }
    });
  });

  // Also, if customer changes mid-way, refresh mapping for all rows (cheap and safe)
  ["Sales Order", "Sales Invoice", "Quotation"].forEach(function(dt) {
    frappe.ui.form.on(dt, {
      customer: function(frm) {
        if (!frm.doc.items || !frm.doc.customer) return;
        const items = Array.from(new Set((frm.doc.items || []).map(r => r.item_code).filter(Boolean)));
        if (!items.length) return;

        frappe.call({
          method: "devp_custom.api.get_item_names_for_customer_batch",
          args: { item_codes: JSON.stringify(items), customer: frm.doc.customer },
          callback: function(r) {
            if (!r || !r.message) return;
            const map = r.message || {};
            (frm.doc.items || []).forEach(function(row) {
              if (!row.item_code) return;
              const res = map[normalize(row.item_code)] || {};
              frappe.model.set_value(row.doctype, row.name, "customer_mapping", res.mapping_name || "");
              if (res.customer_item_name) {
                frappe.model.set_value(row.doctype, row.name, "customer_item_name", res.customer_item_name);
                frappe.model.set_value(row.doctype, row.name, "item_name", res.customer_item_name);
              } else {
                frappe.model.set_value(row.doctype, row.name, "customer_item_name", "");
              }
              if (res.customer_description) {
                frappe.model.set_value(row.doctype, row.name, "customer_description", res.customer_description);
                frappe.model.set_value(row.doctype, row.name, "description", res.customer_description);
              } else {
                frappe.model.set_value(row.doctype, row.name, "customer_description", "");
              }
            });
            frm.refresh_field("items");
          }
        });
      }
    });
  });
})();
