// devp_custom/public/js/sales_invoice_item.js
// Unified last-selling-price popup for Sales Invoice Item, Sales Order Item, Delivery Note Item.

(function () {

    function fetch_prices(item_code, customer, include_other) {
        return frappe.call({
            method: 'devp_custom.api.get_last_item_prices',
            args: {
                item_code: item_code,
                customer: customer,
                limit: 5,
                include_other_customers: include_other ? 1 : 0
            },
            freeze: true,
            freeze_message: include_other
                ? __('Fetching price history from all customers...')
                : __('Fetching last selling prices...')
        });
    }

    function on_item_code(frm, cdt, cdn) {
        const item = locals[cdt][cdn];
        if (!item || !item.item_code) return;

        const customer = frm.doc.customer || '';

        fetch_prices(item.item_code, customer, false)
            .then(function (r) {
                const data = (r && r.message) ? r.message : [];
                if (data.length) {
                    show_last_price_dialog(item, data, false, function () {
                        return fetch_prices(item.item_code, customer, true);
                    });
                    return;
                }
                // No customer-specific history — fallback to all customers
                fetch_prices(item.item_code, customer, true)
                    .then(function (r2) {
                        const other = (r2 && r2.message) ? r2.message : [];
                        if (other.length) {
                            show_last_price_dialog(item, other, true, null);
                        } else {
                            frappe.show_alert({
                                message: __('No previous selling price found for {0}.', [item.item_code]),
                                indicator: 'orange'
                            }, 5);
                        }
                    })
                    .catch(function (err) {
                        console.error('Last prices fallback fetch error', err);
                    });
            })
            .catch(function (err) {
                console.error('Last prices fetch error', err);
            });
    }

    ['Sales Invoice Item', 'Sales Order Item', 'Delivery Note Item'].forEach(function (cdt) {
        frappe.ui.form.on(cdt, { item_code: on_item_code });
    });

    // ----------------------------------------------------------------
    // Dialog
    // ----------------------------------------------------------------
    function show_last_price_dialog(item, data, is_other_party, fetch_other_fn) {
        const rows = map_rows(data);

        const fields = [{
            fieldname: 'prices',
            fieldtype: 'Table',
            cannot_add_rows: true,
            cannot_delete_rows: true,
            in_place_edit: false,
            fields: [
                { label: __('Date'),     fieldname: 'posting_date', fieldtype: 'Date',     in_list_view: 1, read_only: 1 },
                { label: __('Type'),     fieldname: 'doc_type',     fieldtype: 'Data',     in_list_view: 1, read_only: 1 },
                { label: __('Document'), fieldname: 'document',     fieldtype: 'Data',     in_list_view: 1, read_only: 1 },
                { label: __('Customer'), fieldname: 'customer',     fieldtype: 'Data',     in_list_view: 1, read_only: 1 },
                { label: __('Qty'),      fieldname: 'qty',          fieldtype: 'Float',    in_list_view: 1, read_only: 1 },
                { label: __('Rate'),     fieldname: 'rate',         fieldtype: 'Currency', in_list_view: 1, read_only: 1 },
                { label: __('Amount'),   fieldname: 'amount',       fieldtype: 'Currency', in_list_view: 1, read_only: 1 },
                { label: __('Currency'), fieldname: 'currency',     fieldtype: 'Data',     in_list_view: 1, read_only: 1 }
            ],
            data: rows
        }];

        const title_suffix = is_other_party ? ' (' + __('all customers') + ')' : '';
        const dialog_args = {
            title: item.item_code + ' — ' + __('Last Selling Prices') + title_suffix,
            size: 'large',
            fields: fields,
            primary_action_label: __('Use This Rate'),
            primary_action: function () {
                try {
                    const selected = dialog.fields_dict.prices.grid.get_selected_children();
                    if (!selected || selected.length !== 1) {
                        frappe.msgprint(__('Please select exactly one row.'));
                        return;
                    }
                    frappe.model.set_value(item.doctype, item.name, 'rate', selected[0].rate);
                    dialog.hide();
                } catch (e) {
                    console.error('Dialog select error', e);
                }
            }
        };

        if (!is_other_party && typeof fetch_other_fn === 'function') {
            dialog_args.secondary_action_label = __('Show All Customers');
            dialog_args.secondary_action = function () {
                const btn = dialog.wrapper && dialog.wrapper.find('.modal-footer .btn-secondary');
                if (btn && btn.length) btn.prop('disabled', true).text(__('Loading...'));

                fetch_other_fn()
                    .then(function (res) {
                        const other = (res && res.message) ? res.message : [];
                        if (!other.length) {
                            frappe.show_alert({
                                message: __('No price records found from other customers.'),
                                indicator: 'orange'
                            }, 4);
                            if (btn && btn.length) btn.prop('disabled', false).text(__('Show All Customers'));
                            return;
                        }
                        try {
                            const grid = dialog.fields_dict.prices.grid;
                            grid.df.data = map_rows(other);
                            grid.refresh();
                            dialog.set_title(item.item_code + ' — ' + __('Last Selling Prices') + ' (' + __('all customers') + ')');
                            if (btn && btn.length) btn.prop('disabled', true).text(__('Shown'));
                        } catch (e) {
                            console.error('Grid swap error', e);
                            if (btn && btn.length) btn.prop('disabled', false).text(__('Show All Customers'));
                        }
                    })
                    .catch(function (err) {
                        console.error('Other-customers fetch error', err);
                        if (btn && btn.length) btn.prop('disabled', false).text(__('Show All Customers'));
                    });
            };
        }

        const dialog = new frappe.ui.Dialog(dialog_args);
        dialog.show();

        // Auto-select first row for convenience
        try {
            const grid = dialog.fields_dict.prices.grid;
            if (grid && grid.grid_rows && grid.grid_rows[0] && grid.grid_rows[0].row_select_checkbox) {
                grid.grid_rows[0].row_select_checkbox.click();
            }
        } catch (e) {
            console.warn('Auto-select first row failed', e);
        }
    }

    function map_rows(raw) {
        return (raw || []).map(function (r) {
            return {
                posting_date: r.posting_date || '',
                doc_type:     r.doc_type || '',
                document:     r.document || r.invoice || r.order || '',
                customer:     r.customer || '',
                qty:          r.qty || 0,
                rate:         r.rate || 0,
                amount:       r.amount || 0,
                currency:     r.currency || ''
            };
        });
    }

})();
