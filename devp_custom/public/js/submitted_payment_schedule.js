(() => {
    const method = "devp_custom.submitted_payment_schedule.preview_payment_schedule";
    const saved_template = (doc) => doc.__onload?.devp_schedule_template || "";
    const amendment_key = (name) => `devp_custom:due_date_amendment:${frappe.session.user}:${name}`;

    async function apply_schedule(frm, rows) {
        if (rows.some((row) => !row.name)) {
            await frm.set_value("payment_schedule", rows);
            return;
        }

        frappe.model.clear_table(frm.doc, "payment_schedule");
        rows.forEach((row) => frappe.model.add_to_locals(row));
        frm.doc.payment_schedule = rows;
        frm.refresh_field("payment_schedule");
        frm.dirty();
    }

    async function show_schedule_preview(frm, template, preview) {
        await apply_schedule(frm, preview.rows);
        await frm.set_value("due_date", preview.due_date);
        frm.devp_due_date_plan = preview.requires_amendment ? { ...preview, template } : null;
        refresh_actions(frm);
    }

    async function preview_template(frm, doc) {
        const template = doc.payment_terms_template || "";
        const active = frm.devp_schedule_template ?? saved_template(doc);
        const request = (frm.devp_schedule_request || 0) + 1;
        frm.devp_schedule_request = request;
        if (template === active) return;

        const is_current = () => frm.doc === doc && frm.devp_schedule_request === request &&
            (doc.payment_terms_template || "") === template;
        try {
            const preview = await frappe.xcall(method, { invoice_name: doc.name, template });
            if (!is_current()) return;
            await show_schedule_preview(frm, template, preview);
            frm.devp_schedule_template = template;
        } catch (error) {
            if (is_current()) await frm.set_value("payment_terms_template", active);
        }
    }

    function edit_schedule(frm) {
        const doc = frm.doc;
        const template = doc.payment_terms_template || "";
        if (template !== saved_template(doc)) {
            frappe.msgprint(__("Update the invoice to save the selected template before editing its individual payment rows."));
            return;
        }

        const dialog = new frappe.ui.Dialog({
            title: __("Edit Payment Schedule"),
            fields: [{
                fieldname: "schedule",
                fieldtype: "Table",
                cannot_add_rows: true,
                cannot_delete_rows: true,
                in_place_edit: true,
                data: doc.payment_schedule.map((row) => ({
                    schedule_row: row.name,
                    due_date: row.due_date,
                    invoice_portion: row.invoice_portion,
                })),
                fields: [
                    { fieldname: "schedule_row", fieldtype: "Data", hidden: 1 },
                    { fieldname: "due_date", label: __("Due Date"), fieldtype: "Date", in_list_view: 1, reqd: 1 },
                    { fieldname: "invoice_portion", label: __("Invoice Portion"), fieldtype: "Percent", in_list_view: 1, reqd: 1 },
                ],
            }],
            primary_action_label: __("Apply Schedule"),
            async primary_action({ schedule }) {
                const preview = await frappe.xcall(method, {
                    invoice_name: doc.name,
                    template,
                    rows: JSON.stringify(schedule.map((row) => ({
                        name: row.schedule_row,
                        due_date: row.due_date,
                        invoice_portion: row.invoice_portion,
                    }))),
                });
                if (frm.doc !== doc || (doc.payment_terms_template || "") !== template) return;
                await show_schedule_preview(frm, template, preview);
                dialog.hide();
            },
        });
        dialog.show();
    }

    function prepare_due_date_amendment(frm) {
        sessionStorage.setItem(amendment_key(frm.doc.name), JSON.stringify(frm.devp_due_date_plan));
        frappe.msgprint(__(
            "The proposed schedule is ready in this browser tab. Use the invoice’s standard Cancel action, then choose Amend. The amendment draft will open with the proposed schedule and due date for review before submission."
        ));
    }

    function refresh_actions(frm) {
        const field = frm.fields_dict.payment_schedule;
        if (!field) return;
        const grid = field.grid;
        const edit = __("Edit Payment Schedule");
        const amend = __("Prepare Due Date Amendment");
        const permission = frm.perm[0];
        const blocker = frm.doc.__onload?.devp_schedule_blocker;
        const editable = frm.doc.docstatus === 1 && permission?.write && permission.submit &&
            !frm.read_only && field.df.allow_on_submit && blocker === "";
        const can_amend = editable && permission.cancel && permission.amend && permission.create;
        if (frm.doc.docstatus === 1 && field.df.allow_on_submit) {
            const amendment_message = can_amend
                ? __("This preview changes a posted due date. Use Prepare Due Date Amendment to continue.")
                : __("This preview changes a posted due date. Ask a user with Cancel and Amend permissions to review it.");
            const description = blocker || (frm.devp_due_date_plan ? amendment_message :
                frappe.meta.get_docfield(frm.doctype, "payment_schedule").description);
            if (field.df.description !== description) {
                frm.set_df_property("payment_schedule", "description", description);
            }
        }
        if (editable && frm.doc.payment_schedule.length) {
            grid.add_custom_button(edit, () => edit_schedule(frm), "top");
        } else {
            grid.custom_buttons[edit]?.addClass("hidden");
        }
        if (can_amend && frm.devp_due_date_plan) {
            grid.add_custom_button(amend, () => prepare_due_date_amendment(frm), "top");
        } else {
            grid.custom_buttons[amend]?.addClass("hidden");
        }
    }

    frappe.ui.form.on("Sales Invoice", {
        setup(frm) {
            const original = frm.cscript.payment_terms_template;
            frm.cscript.payment_terms_template = function (doc, ...args) {
                if (doc.docstatus === 1) return preview_template(frm, doc);
                return original?.call(this, doc, ...args);
            };
        },
        refresh(frm) {
            frm.devp_schedule_template = saved_template(frm.doc);
            frm.devp_due_date_plan = null;
            refresh_actions(frm);
        },
        async onload_post_render(frm) {
            if (!frm.doc.__islocal || frm.doc.docstatus !== 0 || !frm.doc.amended_from) return;
            const key = amendment_key(frm.doc.amended_from);
            const pending = sessionStorage.getItem(key);
            if (!pending) return;
            const plan = JSON.parse(pending);
            frm.doc.payment_terms_template = plan.template;
            await frm.set_value("payment_schedule", plan.rows);
            await frm.set_value("due_date", plan.due_date);
            frm.refresh_field("payment_terms_template");
            sessionStorage.removeItem(key);
        },
    });
})();
