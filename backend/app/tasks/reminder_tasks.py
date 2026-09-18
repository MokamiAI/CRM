# Celery beat task that scans invoices daily and queues reminder emails
# per configured reminder_rules, guarded against duplicates by the unique
# constraint on reminder_history(invoice_id, reminder_rule_id).
# Implemented in Phase 11 (Automated Reminders).
