# GitHub Actions Alerting

This document lists the optional secrets the deploy workflow can use to push
real-time alerts to your team when something goes wrong on the Aliyun ECS
self-hosted runner.

## `DEPLOY_ALERT_WEBHOOK`

Recommended configuration: the **NotificationConfig webhook URL** configured
in the admin UI (Settings → Notifications). The same endpoint that powers
in-app alerts (企业微信 / 钉钉 / Slack / generic JSON webhook) accepts the
simple `{"text": "..."}` payload posted by the deploy job, so reusing it keeps
your alert routing in one place.

When this secret is **unset**, the deploy failure step silently falls back to
writing the failure context to `${ROLLBACK_LOG_DIR}/deploy-failures.log` on
the runner (and never fails the job because of a missing alert).

When this secret is **set but unreachable** (timeout / non-2xx), the step
also logs a warning and continues — alerts are best-effort and must not
block the workflow run.

Payload posted on failure:

```json
{"text": "🚨 AD-Research deploy FAILED | ref=<github ref> | run=<github run_id>"}
```

## Adding the secret

1. In the GitHub repo: Settings → Secrets and variables → Actions → New
   repository secret.
2. Name: `DEPLOY_ALERT_WEBHOOK`
3. Value: the webhook URL from your NotificationConfig (or any endpoint that
   accepts a JSON body with a `text` field).
