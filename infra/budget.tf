locals {
  # Vertex AI model calls carry no resource labels, so the label filter cannot see them.
  # The second budget filters on the Vertex AI service instead, which also counts other
  # work in the shared project. Verify the service ID in the billing console.
  vertex_service = "services/C7E2-9256-1C43"
}

resource "google_monitoring_notification_channel" "budget" {
  for_each = var.billing_account_id == "" ? toset([]) : toset(var.budget_emails)

  display_name = "Imposter budget ${each.value}"
  type         = "email"
  labels       = { email_address = each.value }

  depends_on = [google_project_service.apis]
}

# Spend on the resources labelled `app=imposter` (Cloud Run, Artifact Registry, ...).
resource "google_billing_budget" "app" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "imposter app resources"

  budget_filter {
    projects = ["projects/${var.project_id}"]
    labels   = var.labels
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [for c in google_monitoring_notification_channel.budget : c.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [google_project_service.apis]
}

resource "google_billing_budget" "vertex" {
  count = var.billing_account_id == "" || var.vertex_budget_amount <= 0 ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "imposter vertex ai (whole project)"

  budget_filter {
    projects = ["projects/${var.project_id}"]
    services = [local.vertex_service]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.vertex_budget_amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [for c in google_monitoring_notification_channel.budget : c.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [google_project_service.apis]
}
