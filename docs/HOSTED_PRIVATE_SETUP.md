# Private accounts on the live site

By default the live site (https://m2o-synthetic-demo.onrender.com) is only the synthetic demo, and it refuses to start if provider credentials are configured. Setting `HOSTED_PRIVATE_ACCOUNTS=true` also serves invited private accounts that connect Jira, Slack, LinkedIn and GitHub, the same way a private local installation does. Decision: Hamza, October 22, 2026.

Visitors keep the credential-free demo either way. Their access is checked per account, not by this switch: every provider path requires a non-visitor account in a non-demo workspace (`is_private_scope`), and `tests/test_visitors.py` proves visitors are refused even with the site-wide demo switch off.

The free host still runs rules extraction and hash retrieval, without recording transcription, MCP tokens or Slack slash commands.

## 1. Make the owner password hash and the encryption key (your laptop)

From `backend`, with its virtual environment:

```
python -m scripts.hosted_secrets
```

It asks for a password twice without echoing it, then prints two lines: `OWNER_PASSWORD_HASH=…` and `PROVIDER_ENCRYPTION_KEY=…`. The password never leaves your laptop; only its Argon2 hash goes to Render.

Keep the encryption key private. It protects the stored provider access, and changing it later disconnects every tool.

## 2. Add the settings in Render

In Render, open the **m2o-synthetic-demo** service and choose **Environment**. Add the following, then **Save changes**; Render redeploys.

| Key                                                                              | Value                                                                                  |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `HOSTED_PRIVATE_ACCOUNTS`                                                        | `true`                                                                                 |
| `OWNER_EMAIL`                                                                    | the email you'll sign in with                                                          |
| `OWNER_NAME`                                                                     | your name (optional)                                                                   |
| `OWNER_PASSWORD_HASH`                                                            | from step 1                                                                            |
| `PROVIDER_ENCRYPTION_KEY`                                                        | from step 1                                                                            |
| `JIRA_CLIENT_ID`, `JIRA_CLIENT_SECRET`                                           | from your Atlassian app (developer console → your app → Settings)                      |
| `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_APP_ID`, `SLACK_SIGNING_SECRET` | from your Slack app (Basic Information → App Credentials)                              |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`                                   | from your LinkedIn app (Auth tab)                                                      |
| `LINKEDIN_PUBLISHING_ENABLED`                                                    | `true` to allow LinkedIn posts                                                         |
| `GITHUB_TOKEN`, `GITHUB_ALLOWED_REPOS`                                           | a fine-grained token with Issues read/write, and the `owner/repo` list it may write to |

These are the same values your local installation uses, so the same provider apps serve both.

The deploy log should say **Hosted owner created.** If it says the configuration is invalid, the message names the setting at fault; values are never printed.

## 3. Register the live callback addresses

Each provider sends you back to M2O after you approve. Add these alongside the `localhost:8080` ones you already have, so local keeps working:

| Provider         | Where                                                                                   | Add                                                                                                                                                                      |
| ---------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Atlassian (Jira) | developer.atlassian.com → your app → **Authorization** → OAuth 2.0 (3LO) → Callback URL | `https://m2o-synthetic-demo.onrender.com/api/integrations/jira/callback`                                                                                                 |
| Slack            | api.slack.com/apps → your app → **OAuth & Permissions** → Redirect URLs                 | `https://m2o-synthetic-demo.onrender.com/api/integrations/slack/callback`                                                                                                |
| LinkedIn         | linkedin.com/developers → your app → **Auth** → Authorized redirect URLs                | `https://m2o-synthetic-demo.onrender.com/api/integrations/linkedin/callback` and `https://m2o-synthetic-demo.onrender.com/api/integrations/linkedin/publishing/callback` |
| GitHub           | nothing to register                                                                     | M2O uses the token directly                                                                                                                                              |

If a console accepts only one callback URL, create a second app for the live site and use its keys in Render.

## 4. Sign in and connect

1. Open the live site and sign in with `OWNER_EMAIL` and your password. You'll find three workspaces, as locally.
2. Optionally delete `OWNER_PASSWORD_HASH` from Render. The account stays, and a later start never changes an existing password.
3. Connect each tool from the sidebar or **Settings → Connections**. Consent opens in a new tab.

## 5. Invite people

**Settings → Access** creates an invitation link for a workspace and role. Send it yourself; the person opens it, chooses their own password and signs in.

| Tool     | Can an invitee connect their own account?                                                                                                                                                                                                                                                                       |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LinkedIn | Yes: any LinkedIn member can approve your app.                                                                                                                                                                                                                                                                  |
| Jira     | Only after you switch your Atlassian app to **Sharing** (developer console → Distribution). That asks for a vendor name, a privacy policy URL (`https://m2o-synthetic-demo.onrender.com/privacy.html`) and a personal-data declaration. It is not a Marketplace listing. Until then, only you can authorize it. |
| Slack    | People in your Slack workspace can. Other workspaces need **Manage Distribution → Activate Public Distribution**. This doesn't list the app in the App Directory.                                                                                                                                               |
| GitHub   | No. Deliveries use your token, into the repositories in `GITHUB_ALLOWED_REPOS`, in workspaces whose owner binds one. List only repositories you're happy for invitees to file issues in.                                                                                                                        |

Within a workspace, only its owner connects Jira and Slack, and deliveries use that connection. LinkedIn connects per person.

## Data and backups

Private data lives in the Neon free database. Neon keeps a short restore history, which you can check in the Neon console (Project → Backup & Restore), but there are no scheduled backups. Before relying on it, export important workspaces from **Settings → Privacy** now and then.

Before you share the privacy page, read it and replace its placeholder contact address (`privacy@example.invalid`, in `frontend/public/privacy.html`).

## Turning it off

Delete `HOSTED_PRIVATE_ACCOUNTS` and every provider and owner setting in Render. With the switch off, the site refuses to start while any of them remain, which keeps the demo credential-free.
