app_name = "devp_custom"
app_title = "Devp Custom"
app_publisher = "Mradul Mishra"
app_description = "Devp Custom"
app_email = "mradulmishra010@gmail.com"
app_license = "mit"

fixtures = ["Custom Field"]

# apps/devp_custom/devp_custom/hooks.py
# hooks.py

# apps/devp_custom/hooks.py
doctype_js = {
    "Item": "public/js/item_client.js",
    "Sales Order": "public/js/sales_order_item.js",
    "Quotation": "public/js/quotation_item_last_prices.js",
    "Sales Invoice": [
        "public/js/sales_invoice_item.js",
        "public/js/sales_invoice_batch_dates.js"
    ]
}


# in hooks.py
doc_events = {
    "Item": {
        "before_insert": "devp_custom.api.assign_item_code_before_insert",
        # previous hooks removed/kept as needed; add:
        "on_submit": "devp_custom.api.auto_set_item_code_on_submit"
    },
    "Sales Invoice Item": {
        "validate": "devp_custom.overrides.sales_invoice_item.calculate_amount"
    },
    "Work Order": {
        "validate": "devp_custom.api.validate_work_order_batch_size"
    },
    "Sales Invoice": {
        "validate": "devp_custom.api.validate_sales_invoice_batch_size"
    },
}

app_include_js = [
    "public/js/sales_invoice_item.js",
    
]





# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "devp_custom",
# 		"logo": "/assets/devp_custom/logo.png",
# 		"title": "Devp Custom",
# 		"route": "/devp_custom",
# 		"has_permission": "devp_custom.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/devp_custom/css/devp_custom.css"
# app_include_js = "/assets/devp_custom/js/devp_custom.js"

# include js, css files in header of web template
# web_include_css = "/assets/devp_custom/css/devp_custom.css"
# web_include_js = "/assets/devp_custom/js/devp_custom.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "devp_custom/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "devp_custom/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "devp_custom.utils.jinja_methods",
# 	"filters": "devp_custom.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "devp_custom.install.before_install"
# after_install = "devp_custom.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "devp_custom.uninstall.before_uninstall"
# after_uninstall = "devp_custom.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "devp_custom.utils.before_app_install"
# after_app_install = "devp_custom.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "devp_custom.utils.before_app_uninstall"
# after_app_uninstall = "devp_custom.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "devp_custom.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"devp_custom.tasks.all"
# 	],
# 	"daily": [
# 		"devp_custom.tasks.daily"
# 	],
# 	"hourly": [
# 		"devp_custom.tasks.hourly"
# 	],
# 	"weekly": [
# 		"devp_custom.tasks.weekly"
# 	],
# 	"monthly": [
# 		"devp_custom.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "devp_custom.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "devp_custom.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "devp_custom.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["devp_custom.utils.before_request"]
# after_request = ["devp_custom.utils.after_request"]

# Job Events
# ----------
# before_job = ["devp_custom.utils.before_job"]
# after_job = ["devp_custom.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"devp_custom.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

