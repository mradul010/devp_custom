// // devp_custom/public/js/last_item_prices_all.js
// // Handles Sales Invoice Item, Sales Order Item, Quotation Item
// // Behavior:
// // 1) Try fetching last prices for current customer/party
// // 2) If none, fetch last prices from other parties
// // 3) Show dialog with Invoice, Date, Party, Rate; select one to set row.rate

// (function() {
//   function get_parent_customer(frm) {
//     // try common parent fields across Sales Invoice / Sales Order / Quotation
//     return frm.doc.customer || frm.doc.party_name || frm.doc.party || "";
//   }

//   function build_and_show_dialog(frm, item, rows, is_other_party) {
//     if (!rows || !rows.length) {
//       frappe.msgprint({ title: 'No history', message: `No sales history found for ${item.item_code}`, indicator: 'orange' });
//       return;
//     }

//     const fields = [{
//       fieldname: 'prices',
//       fieldtype: 'Table',
//       cannot_add_rows: true,
//       cannot_delete_rows: true,
//       in_place_edit: false,
//       fields: [
//         { label: 'Invoice',      fieldname: 'invoice',      fieldtype: 'Link',   options: 'Sales Invoice', in_list_view:1, read_only:1 },
//         { label: 'Invoice Date', fieldname: 'posting_date', fieldtype: 'Date',                   in_list_view:1, read_only:1 },
//         { label: 'Party',        fieldname: 'customer',     fieldtype: 'Data',                   in_list_view:1, read_only:1 },
//         { label: 'Rate',         fieldname: 'rate',         fieldtype: 'Currency',               in_list_view:1, read_only:1 }
//       ],
//       data: rows
//     }];

//     const title_extra = is_other_party ? ' (from other parties)' : '';
//     const d = new frappe.ui.Dialog({
//       title: `${item.item_code} — Last Selling Prices${title_extra}`,
//       size: 'large',
//       fields: fields,
//       primary_action_label: 'Select',
//       primary_action: function() {
//         try {
//           const selected = d.fields_dict.prices.grid.get_selected_children();
//           if (!selected || selected.length !== 1) {
//             frappe.msgprint('Please select exactly one row to pick the rate.');
//             return;
//           }
//           const chosen = selected[0];
//           frappe.model.set_value(item.doctype, item.name, 'rate', chosen.rate);
//           d.hide();
//         } catch (e) {
//           console.error('Dialog select error', e);
//           frappe.msgprint('Could not set rate — see console.');
//         }
//       }
//     });

//     d.show();

//     // auto-select first row for convenience
//     try {
//       const grid = d.fields_dict.prices.grid;
//       if (grid && grid.grid_rows && grid.grid_rows.length) {
//         const firstRow = grid.grid_rows[0];
//         if (firstRow && firstRow.row_select_checkbox) {
//           firstRow.row_select_checkbox.click();
//           grid.wrapper && grid.wrapper.scrollTop(0);
//         }
//       }
//     } catch (e) {
//       console.warn('Auto-select failed', e);
//     }
//   }

//   async function fetch_and_show(frm, cdt, cdn) {
//     const item = locals[cdt][cdn];
//     if (!item || !item.item_code) return;

//     const parent_customer = get_parent_customer(frm) || "";

//     // first try same customer
//     try {
//       const resp = await frappe.call({
//         method: 'devp_custom.api.get_last_item_prices',
//         args: {
//           item_code: item.item_code,
//           customer: parent_customer,
//           limit: 5,
//           include_other_customers: false
//         },
//         freeze: false
//       });

//       const data = (resp && resp.message) ? resp.message : [];
//       if (data.length) {
//         build_and_show_dialog(frm, item, data, false);
//         return;
//       }

//       // no data for this customer — fetch other customers
//       const resp2 = await frappe.call({
//         method: 'devp_custom.api.get_last_item_prices',
//         args: {
//           item_code: item.item_code,
//           customer: parent_customer,
//           limit: 5,
//           include_other_customers: true
//         },
//         freeze: false
//       });

//       const other = (resp2 && resp2.message) ? resp2.message : [];
//       if (other.length) {
//         build_and_show_dialog(frm, item, other, true);
//       } else {
//         frappe.msgprint({ title: 'No history', message: `No sales history found for ${item.item_code}`, indicator: 'orange' });
//       }
//     } catch (err) {
//       console.error('Error fetching last prices', err);
//       frappe.msgprint({ title: 'Error', message: 'Failed to fetch last prices. See console.' });
//     }
//   }

//   // attach same handler to all three child doctypes
//   frappe.ui.form.on('Sales Invoice Item', { item_code: function(frm, cdt, cdn){ fetch_and_show(frm, cdt, cdn); }});
//   frappe.ui.form.on('Sales Order Item',   { item_code: function(frm, cdt, cdn){ fetch_and_show(frm, cdt, cdn); }});
//   frappe.ui.form.on('Quotation Item',     { item_code: function(frm, cdt, cdn){ fetch_and_show(frm, cdt, cdn); }});

// })();
