// devp_custom/public/js/sales_order_item.js
// Updated: default fetch for the current customer, plus a "Show other parties" button
// If current customer has no sales history, caller code still tries other customers as fallback.
// Additionally, caller can pass allow_other_button=true to let user request other-party data on demand.

frappe.ui.form.on('Sales Order Item', {
    item_code: function(frm, cdt, cdn) {
        const item = locals[cdt][cdn];
        if (!item || !item.item_code) return;

        // send empty string if no customer to avoid sending "null"
        const customer = frm.doc.customer || "";

        const fetchForCustomer = () => {
            return frappe.call({
                method: 'devp_custom.api.get_last_item_prices',
                args: {
                    item_code: item.item_code,
                    customer: customer,
                    limit: 5,
                    include_other_customers: false
                },
                freeze: true,
                freeze_message: 'Fetching last selling prices...'
            });
        };

        // note: keep fetchOtherCustomers here so show_price_dialog can optionally call it
        const fetchOtherCustomers = () => {
            return frappe.call({
                method: 'devp_custom.api.get_last_item_prices',
                args: {
                    item_code: item.item_code,
                    customer: customer,
                    limit: 50, // when fetching "all", increase limit as you see fit
                    include_other_customers: true
                },
                freeze: true,
                freeze_message: 'Fetching last selling prices from other parties...'
            });
        };

        // First try for this customer
        fetchForCustomer().then(r => {
            const data = (r && r.message) ? r.message : [];
            if (data.length) {
                // show dialog with a button to fetch other-party data if desired
                show_price_dialog(frm, item, data, true, false, fetchOtherCustomers);
            } else {
                // No history for this customer — fetch other customers' last prices immediately
                fetchOtherCustomers().then(res2 => {
                    const other = (res2 && res2.message) ? res2.message : [];
                    if (other.length) {
                        // show dialog with other-party data; indicate it's from other parties
                        show_price_dialog(frm, item, other, false, true, null);
                    } else {
                        // nothing anywhere
                        frappe.msgprint({
                            title: 'No history',
                            message: `No sales history found for ${item.item_code} (neither for this customer nor other customers).`,
                            indicator: 'orange'
                        });
                    }
                }).catch(err2 => {
                    console.error('Error fetching other-party prices', err2);
                    frappe.msgprint({ title: 'Error', message: 'Failed to fetch other-party prices. See console.' });
                });
            }
        }).catch(err => {
            console.error('Error fetching last prices', err);
            frappe.msgprint({
                title: 'Error',
                message: 'Failed to fetch last prices. See console.'
            });
        });
    }
});

/**
 * show_price_dialog
 *  - frm, item: as usual
 *  - data: array of records to show
 *  - allow_other_button: boolean, if true show a "Show other parties" secondary action
 *  - is_other_party: boolean, whether `data` already contains other-party results
 *  - fetchOtherCustomersFn: optional function that returns a promise resolving to server results (useful for the button)
 */
function show_price_dialog(frm, item, data, allow_other_button=false, is_other_party=false, fetchOtherCustomersFn=null) {
    // data expected: [{ order|invoice, posting_date, rate, customer }, ...]
    // fields: use 'order' Link to Sales Order (backend can return invoice/order but we show it as generic id)
    const fields = [{
        fieldname: 'prices',
        fieldtype: 'Table',
        cannot_add_rows: true,
        cannot_delete_rows: true,
        in_place_edit: false,
        fields: [
            {
                label: 'Document',
                fieldname: 'document',
                fieldtype: 'Data',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Date',
                fieldname: 'posting_date',
                fieldtype: 'Date',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Party',
                fieldname: 'customer',
                fieldtype: 'Data',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Rate',
                fieldname: 'rate',
                fieldtype: 'Currency',
                in_list_view: 1,
                read_only: 1
            }
        ],
        data: map_data_for_dialog(data)
    }];

    const title_extra = is_other_party ? ' (from other parties)' : '';
    const dialog_args = {
        title: `${item.item_code} — Last Selling Prices${title_extra}`,
        size: 'large',
        fields: fields,
        primary_action_label: 'Select',
        primary_action: function() {
            try {
                const selected = dialog.fields_dict.prices.grid.get_selected_children();
                if (!selected || selected.length !== 1) {
                    frappe.msgprint('Please select exactly one row to pick the rate.');
                    return;
                }
                const chosen = selected[0];
                // set rate on the Sales Order Item row
                frappe.model.set_value(item.doctype, item.name, 'rate', chosen.rate);
                // if you need to trigger recalculation of amounts, you can do:
                // frm.script_manager.trigger("calculate_taxes_and_totals"); // example
                dialog.hide();
            } catch (e) {
                console.error('Dialog select error', e);
                frappe.msgprint('Could not set rate — see console.');
            }
        }
    };

    // if allowed and we're not already showing other-party data, provide secondary action to fetch
    if (allow_other_button && !is_other_party && typeof fetchOtherCustomersFn === 'function') {
        dialog_args.secondary_action_label = 'Show other parties';
        dialog_args.secondary_action = function() {
            // disable the button immediately to prevent double clicks
            const btn = dialog.wrapper && dialog.wrapper.find('.modal-footer .btn-secondary');
            if (btn && btn.length) btn.prop('disabled', true).text('Loading...');
            // call the provided fetch function
            fetchOtherCustomersFn().then(res => {
                const other = (res && res.message) ? res.message : [];
                if (!other.length) {
                    frappe.msgprint({ title: 'No history', message: 'No records found from other parties.' });
                    // re-enable button
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                    return;
                }
                // update data in the table grid
                try {
                    const grid = dialog.fields_dict.prices.grid;
                    grid.wrapper && grid.wrapper.scrollTop(0);
                    // map new data for dialog fields (ensure consistent keys)
                    grid.df.data = map_data_for_dialog(other);
                    // refresh grid to show new rows
                    grid.refresh();
                    // update dialog title to indicate other-party data
                    dialog.set_title(`${item.item_code} — Last Selling Prices (from other parties)`);
                    // hide/disable the secondary button since it's now showing other-party data
                    if (btn && btn.length) {
                        btn.prop('disabled', true).text('Shown');
                    }
                } catch (e) {
                    console.error('Failed to swap grid data', e);
                    frappe.msgprint({ title: 'Error', message: 'Failed to display other-party data. See console.' });
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                }
            }).catch((err) => {
                console.error('Error fetching other-party prices', err);
                frappe.msgprint({ title: 'Error', message: 'Failed to fetch other-party prices. See console.' });
                if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
            });
        };
    }

    const dialog = new frappe.ui.Dialog(dialog_args);

    dialog.show();

    // auto-select first row for convenience
    try {
        const grid = dialog.fields_dict.prices.grid;
        if (grid && grid.grid_rows && grid.grid_rows.length) {
            const firstRow = grid.grid_rows[0];
            if (firstRow && firstRow.row_select_checkbox) {
                firstRow.row_select_checkbox.click();
                grid.wrapper && grid.wrapper.scrollTop(0);
            }
        }
    } catch (e) {
        console.warn('Auto-select failed', e);
    }

    // helper: uniform mapping so dialog fields use 'document' key (works whether backend returns invoice/order/etc.)
    function map_data_for_dialog(raw) {
        // raw records might have 'invoice' or 'order' or similar; normalize to dialog fields
        return (raw || []).map(r => {
            return {
                document: r.invoice || r.order || r.name || '',
                posting_date: r.posting_date || r.transaction_date || r.date || '',
                customer: r.customer || r.party || '',
                rate: r.rate || r.price || 0
            };
        });
    }
}
