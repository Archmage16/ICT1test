# OlympIQ UX Sprint on Render

This branch preserves the original Django interface and includes the eligibility-message improvement.
`render.yaml` defines a free web service and a separate free PostgreSQL database.
It does not use Vercel or depend on a local computer staying online.

Create a Render Blueprint from this repository and select `ux-sprint-render`.
Review the plans before creating resources: both must remain **Free**.
Render generates the secret key and supplies database credentials automatically.
The production server runs with `DJANGO_DEBUG=false`, secure cookies and HTTPS redirects.

The database is a dedicated public demonstration sandbox, not a production student database.
Initialization creates 24 visibly marked sample events and student test accounts
`ux01`, `ux02`, `ux03` (password `Demo12345!`). Reserve `uxcheck` for technical checks.
The default administrator and teacher accounts are disabled and have unusable passwords.
Do not upload real student information or reuse personal passwords in this public sandbox.
Do not expose `.env`, the local SQLite database, or Telegram credentials.

Render Free limitations: the web service sleeps after 15 minutes of inactivity and
may take about a minute to wake. Free PostgreSQL expires 30 days after creation.
These limits make this a short-term coursework demo, not permanent production hosting.
Record and export anonymous usability observations outside the demo database.

After deployment, verify the public home page, catalogue, sign-in, one application,
dashboard status and the incompatible-grade recovery link. Only then add the
server-returned `https://…onrender.com/` address to the shared assignment document.

References: https://render.com/docs/deploy-django and https://render.com/docs/free
