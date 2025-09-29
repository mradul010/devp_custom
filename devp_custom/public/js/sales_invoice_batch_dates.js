// Auto-fill Batch Expiry & Manufacturing dates on Sales Invoice Item from selected Batch

frappe.ui.form.on('Sales Invoice Item', {
  // Clear when item changes
  item_code(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, 'batch_expiry_date', null);
    frappe.model.set_value(cdt, cdn, 'batch_manufacturing_date', null);
  },

  // Fill when batch selected
  batch_no(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.batch_no) {
      frappe.model.set_value(cdt, cdn, 'batch_expiry_date', null);
      frappe.model.set_value(cdt, cdn, 'batch_manufacturing_date', null);
      return;
    }
    frappe.db.get_value('Batch', row.batch_no, ['expiry_date', 'manufacturing_date'])
      .then(r => {
        const d = r.message || {};
        frappe.model.set_value(cdt, cdn, 'batch_expiry_date', d.expiry_date || null);
        frappe.model.set_value(cdt, cdn, 'batch_manufacturing_date', d.manufacturing_date || null);
      });
  }
});

// (Optional) Also fetch via add_fetch so it fills on load/refresh too
frappe.ui.form.on('Sales Invoice', {
  setup(frm) {
    frm.add_fetch('batch_no', 'expiry_date', 'batch_expiry_date');
    frm.add_fetch('batch_no', 'manufacturing_date', 'batch_manufacturing_date');
  }
});
