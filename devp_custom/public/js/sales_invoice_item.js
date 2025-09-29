// devp_custom/public/js/last_prices_for_line_items.js
// Unified script: shows last selling prices for Sales Order Item and Sales Invoice Item rows.
// Default: show prices for current customer; user can click "Show other parties" to fetch all history.

// Register handlers for both child doctypes
['Sales Order Item', 'Sales Invoice Item'].forEach(function(childDoctype) {
    frappe.ui.form.on(childDoctype, {
        item_code: function(frm, cdt, cdn) {
            const item = locals[cdt][cdn];
            if (!item || !item.item_code) return;

            const customer = frm.doc.customer || "";

            // small helper to determine which document link to display in dialog
            const docLinkLabel = (childDoctype === 'Sales Order Item') ? 'Sales Order' : 'Sales Invoice';

            const fetchForCustomer = (limit=5) => {
                return frappe.call({
                    method: 'devp_custom.api.get_last_item_prices',
                    args: {
                        item_code: item.item_code,
                        customer: customer,
                        limit: limit,
                        include_other_customers: false
                    },
                    freeze: true,
                    freeze_message: 'Fetching last selling prices...'
                });
            };

            const fetchOtherCustomers = (limit=50) => {
                return frappe.call({
                    method: 'devp_custom.api.get_last_item_prices',
                    args: {
                        item_code: item.item_code,
                        customer: customer,
                        limit: limit,
                        include_other_customers: true
                    },
                    freeze: true,
                    freeze_message: 'Fetching last selling prices from other parties...'
                });
            };

            // default behavior: try for this customer first
            fetchForCustomer().then(function(r) {
                const data = (r && r.message) ? r.message : [];
                if (data.length) {
                    // show dialog for current customer, but allow user to fetch other parties if they want
                    open_last_price_dialog({
                        frm, item, data,
                        docLinkLabel,
                        allow_other_button: true,
                        is_other_party: false,
                        fetchOtherCustomersFn: () => fetchOtherCustomers(50)
                    });
                } else {
                    // no history for this customer — fetch other-party data immediately (fallback)
                    fetchOtherCustomers(50).then(function(r2){
                        const other = (r2 && r2.message) ? r2.message : [];
                        if (other.length) {
                            open_last_price_dialog({
                                frm, item, data: other,
                                docLinkLabel,
                                allow_other_button: false,
                                is_other_party: true,
                                fetchOtherCustomersFn: null
                            });
                        } else {
                            frappe.msgprint({
                                title: 'No history',
                                message: `No sales history found for ${item.item_code} (neither for this customer nor other customers).`,
                                indicator: 'orange'
                            });
                        }
                    }).catch(function(err2){
                        console.error('Error fetching other-party prices', err2);
                        frappe.msgprint({ title: 'Error', message: 'Failed to fetch other-party prices. See console.' });
                    });
                }
            }).catch(function(err){
                console.error('Error fetching last prices', err);
                frappe.msgprint({ title: 'Error', message: 'Failed to fetch last prices. See console.' });
            });
        }
    });
});

/**
 * open_last_price_dialog(options)
 * options:
 *  - frm, item, data (array)
 *  - docLinkLabel: 'Sales Order' or 'Sales Invoice' (used in Link column)
 *  - allow_other_button: boolean (show "Show other parties" secondary action)
 *  - is_other_party: boolean (data already from other parties)
 *  - fetchOtherCustomersFn: function() => Promise resolving to frappe.call result (used by secondary button)
 */
function open_last_price_dialog(options) {
    const { frm, item, data, docLinkLabel, allow_other_button=false, is_other_party=false, fetchOtherCustomersFn=null } = options;

    // Build dialog fields: first column is Link to appropriate document type
    const fields = [{
        fieldname: 'prices',
        fieldtype: 'Table',
        cannot_add_rows: true,
        cannot_delete_rows: true,
        in_place_edit: false,
        fields: [
            {
                label: docLinkLabel,
                fieldname: 'document',
                fieldtype: 'Link',
                options: docLinkLabel,
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
                // set rate on the child row (works for both Sales Order Item & Sales Invoice Item)
                frappe.model.set_value(item.doctype, item.name, 'rate', chosen.rate);
                // optionally trigger recalculation if your child row depends on it
                // Example (uncomment if needed):
                // frm.script_manager.trigger('calculate_taxes_and_totals');
                dialog.hide();
            } catch (e) {
                console.error('Dialog select error', e);
                frappe.msgprint('Could not set rate — see console.');
            }
        }
    };

    if (allow_other_button && !is_other_party && typeof fetchOtherCustomersFn === 'function') {
        dialog_args.secondary_action_label = 'Show other parties';
        dialog_args.secondary_action = function() {
            // disable button immediately
            const btn = dialog.wrapper && dialog.wrapper.find('.modal-footer .btn-secondary');
            if (btn && btn.length) btn.prop('disabled', true).text('Loading...');
            fetchOtherCustomersFn().then(function(res) {
                const other = (res && res.message) ? res.message : [];
                if (!other.length) {
                    frappe.msgprint({ title: 'No history', message: 'No records found from other parties.' });
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                    return;
                }
                try {
                    const grid = dialog.fields_dict.prices.grid;
                    grid.wrapper && grid.wrapper.scrollTop(0);
                    grid.df.data = map_data_for_dialog(other);
                    grid.refresh();
                    dialog.set_title(`${item.item_code} — Last Selling Prices (from other parties)`);
                    if (btn && btn.length) {
                        btn.prop('disabled', true).text('Shown');
                    }
                } catch (e) {
                    console.error('Failed to swap grid data', e);
                    frappe.msgprint({ title: 'Error', message: 'Failed to display other-party data. See console.' });
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                }
            }).catch(function(err){
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

    // helper to normalize backend data for dialog
    function map_data_for_dialog(raw) {
        return (raw || []).map(function(r) {
            // prefer invoice/order/name keys for the Link column; 'document' key used by grid df
            return {
                document: r.invoice || r.order || r.name || '',
                posting_date: r.posting_date || r.transaction_date || r.date || '',
                customer: r.customer || r.party || '',
                rate: r.rate || r.price || 0
            };
        });
    }
}
