# Provider account setup

October 3 update: Jira's local OAuth/account storage, site discovery, destination verification and workspace disconnect are implemented. Follow [JIRA_CONNECTION.md](JIRA_CONNECTION.md) for the executable setup and current boundary; the older Jira checklist below is background. Issue delivery and live provider verification are still pending. Hamza has reported creating the Slack/Jira test applications; this repository did not perform those account actions.

This document and `integrations/slack/manifest.json` prepare account setup. They do not create accounts/apps or implement Jira/Slack delivery. No provider credentials exist in this repository's tracked configuration. Never paste a secret into chat or commit one.

## Slack test application

1. Sign in to a Slack workspace where you can install an app. Create a dedicated synthetic testing workspace/channel if needed; do not start in an employer's workspace.
2. Open [Slack Your Apps](https://api.slack.com/apps), choose Create New App → From a manifest, select that test workspace and import `integrations/slack/manifest.json`.
3. Check that the requested bot scope is only `chat:write`. This initial configuration does not request channel history, direct-message history, workspace-wide public posting or events.
4. Install the app to the test workspace. Privately retain the bot credential in the application operator's secret configuration once the delivery adapter is ready. Do not put it in the frontend or this manifest.
5. Invite the bot to one dedicated test channel. Record its channel ID as an allowed destination, paired to the M2O workspace. Do not infer access to every Slack channel from workspace membership.
6. Once the adapter exists and is locally tested, explicitly authorize a synthetic live send and verify the provider receipt. Current M2O still marks Slack delivery unavailable.

The manifest is for a manually installed test bot. It does not implement multi-workspace OAuth installation. That later flow needs the actual HTTPS redirect URL, state validation, securely stored provider credentials and revocation handling. Token rotation is disabled in this manifest because rotating-token support has not been implemented; this is a stated limitation, not an enterprise configuration claim.

References: [App manifests](https://docs.slack.dev/app-manifests/), [manifest reference](https://docs.slack.dev/reference/app-manifest/), [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/).

## Jira test application

1. Sign in to Atlassian and establish a Jira Cloud test site/project that you own. Creating a developer app alone does not create a destination project.
2. In the [developer console](https://developer.atlassian.com/console/myapps/), create an OAuth 2.0 integration for M2O when implementing multi-user authorization. Configure the Jira API permissions actually needed for the chosen endpoints. Issue creation requires project Browse/Create permissions and the relevant write scope; field discovery may need read access.
3. Set the redirect URL only after the backend callback exists and the actual local/public origin is known. The configured callback must exactly match the authorization flow. No invented Render domain is supplied here.
4. Record the actual site/cloud ID, project key, issue type ID and required custom fields. Validate available fields rather than assuming every project accepts the same issue structure. Descriptions use Atlassian Document Format.
5. Keep client credentials and refresh/access credentials exclusively in backend secrets. The application needs authorization-state validation, destination allow-lists, token lifecycle handling and explicit approval of the final issue payload.
6. Authorize a synthetic live create only after the adapter, exact preview and failure handling pass local tests. Current M2O still marks Jira delivery unavailable.

References: [OAuth 2.0 integrations](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/), [issue creation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).

## LinkedIn

The current connection requests OpenID Connect self-profile scopes only. Posting is a distinct capability requiring the Share on LinkedIn product and `w_member_social`, a member-authorized token, an exact approved post and a retained publication receipt. Do not broaden the current OIDC settings and assume posting then works: the current implementation intentionally does not retain a posting token.

Lead-message drafting can be local and human-reviewed. Actual LinkedIn message sending requires a separately supported approved access path; ordinary OIDC and posting permissions do not establish that access. No message sender or post adapter has been implemented by this setup preparation.

References: [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin), [API access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access).

## Provider account actions

Local preparation is complete for the Slack test-bot manifest and documented Jira setup. Account registration, workspace/site creation, app installation, legal agreements, permission grants and secret provisioning still require the signed-in human account. Do not claim those actions are completed from configuration files alone.
