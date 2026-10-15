# M2O privacy policy

Last updated: October 15, 2026

M2O (Meeting 2 Outcomes) is an open-source portfolio project by Hamza ([@hs14235](https://github.com/hs14235)). It turns meeting transcripts into reviewed action items. This policy covers the public demo at `m2o-synthetic-demo.onrender.com` and private installations run by the author. Anyone who runs their own copy of M2O is responsible for their own installation.

## The public demo

- The demo uses **synthetic, invented data only**. Please do not enter real meeting content or personal information.
- Each visitor gets temporary isolated workspaces. Visitor access expires after two hours. Expired demo data is then removed by operator cleanup, and the demo database is disposable.
- The demo has **no connections to LinkedIn, Jira, Slack, GitHub or Google** and refuses to start if any provider credentials are configured.
- The server keeps short-lived technical records needed to run the service: a session cookie, rate-limit counters derived from network addresses, and request logs (method, route, status, timing). Logs do not contain transcript content.

## LinkedIn

LinkedIn features run only in a private installation, only for a signed-in account owner or reviewer, and only after that person explicitly connects their own LinkedIn account.

- **What M2O receives:** your LinkedIn member identifier and basic profile (name) through Sign In with LinkedIn using OpenID Connect, and an access token that permits posting on your behalf (`w_member_social`).
- **How it is stored:** the access token and your author identifier are encrypted in the M2O database. They are never shown in the interface or written to logs.
- **What M2O does with it:** it publishes a text post to your own LinkedIn account **only** after you write or review the exact text, see a preview showing the audience, and approve it. Posts default to your connections only. M2O does not read your feed, connections or messages, does not message anyone, and does not post automatically.
- **Removing access:** disconnecting LinkedIn in M2O deletes the stored token. You can also revoke M2O at any time in your LinkedIn settings under *Data privacy → Permitted services*. Posts that were already published stay on LinkedIn until you delete them there.

## Other data in private installations

Private installations store the transcripts, outcomes, review history and plans that their users enter, in the installation's own PostgreSQL database. Audio uploaded for transcription is processed on the same machine and deleted after transcription. Workspace owners can erase a workspace, and users can erase their account; see [the user lifecycle documentation](docs/USER_LIFECYCLE.md) for exactly what is removed and what is retained.

## Sharing

M2O does not sell data, show ads or use analytics or tracking scripts. Data leaves an installation only when a user approves a specific delivery to a connected tool (for example a LinkedIn post or a Jira issue).

## Contact

Questions or deletion requests: open an issue at [github.com/hs14235/M2O/issues](https://github.com/hs14235/M2O/issues) or contact the author through their GitHub profile.
