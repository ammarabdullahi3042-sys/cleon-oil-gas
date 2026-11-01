# CLEON website member portal setup (free test deployment)

The website now targets a Supabase Edge Function for the member portal and a
Netlify static build for hosting. Netlify Free currently has a $0 monthly plan
with a 300-credit hard monthly limit; if its included usage is exhausted, the
site can stop serving until the next cycle rather than accruing a bill. Supabase
usage is also subject to the current project quotas and inactivity policies.

## 1. Apply the database migration

From this project folder, install the Supabase CLI if it is not already
available, then authenticate and link the existing CLEON project:

```powershell
supabase login
supabase link --project-ref efpocgthifwgzgnuwgae
supabase db push
```

The migration creates the portal role, snapshot, and document tables, enables
RLS, makes the documents bucket private, and assigns the existing verified
`ammarabdullahi3042@gmail.com` Auth user the `super_admin` portal role if that
Auth user exists. It does not create or change a password. If the user does not
exist at migration time, create/verify the Auth user first, then run the
provided role insert from the migration in the SQL Editor.

## 2. Configure and deploy the Edge Function

Create a long random publisher token and keep it private. In PowerShell, set it
as a Supabase Function secret (replace the placeholder locally; do not commit it):

```powershell
$env:CLEON_WEBSITE_PUBLISH_TOKEN = '<long-random-token>'
supabase secrets set CLEON_WEBSITE_PUBLISH_TOKEN="$env:CLEON_WEBSITE_PUBLISH_TOKEN" --project-ref efpocgthifwgzgnuwgae
supabase functions deploy cleon-portal --project-ref efpocgthifwgzgnuwgae
```

The project URL and Supabase Auth keys are injected by Supabase. The Edge
Function uses the server-side service key only inside Supabase and never puts it
in website HTML. `verify_jwt = false` is set for this function because its
routes perform their own Auth checks; the publish routes require the private
publisher token.

## 3. Host the static website on Netlify Free

Import the GitHub repository that contains the website into Netlify and deploy
from its repository root. The included `netlify.toml` runs `python
build_website.py`, publishes `website-build`, and injects the function endpoint:

`https://efpocgthifwgzgnuwgae.supabase.co/functions/v1/cleon-portal`

The selected OneDrive page has been copied to this project's `website/index.html`
and is included in the generated `website-build` output. This ERP checkout has
no Git remote configured, so it is not yet connected to the existing GitHub
Pages repository or Netlify.

After deployment, the enquiry inbox is available at `/admin.html`; it uses the
existing Supabase Auth login and admin allowlist policies. Do not add a service
key to that page.

## 4. Connect the desktop ERP publisher

On the Windows computer running CLEON Fuel Station ERP, set these user
environment variables:

- `CLEON_WEBSITE_API_URL` = `https://efpocgthifwgzgnuwgae.supabase.co/functions/v1/cleon-portal`
- `CLEON_WEBSITE_PUBLISH_TOKEN` = the same private token saved as a Supabase
  Function secret

Restart the ERP after setting them. Open Dashboard and Report Centre so the app
publishes the latest dashboard and report snapshots. The desktop publisher
sends the public Supabase publishable key plus the private bearer token; only
the private token authorizes publishing.

## 5. Member accounts

The account used to sign in must exist in Supabase Authentication and have an
active row in `public.website_member_roles`. The migration seeds the existing
owner email as `super_admin`. To add a member, create their Auth account first,
then run a role insert in the Supabase SQL Editor, for example:

```sql
insert into public.website_member_roles (user_id, role, active)
select id, 'member', true
from auth.users
where lower(email) = lower('member@example.com')
on conflict (user_id) do update
set role = excluded.role, active = true;
```

Never place a Supabase secret/service key, member password, or publisher token
in website HTML or GitHub. Only the publishable key belongs in browser code.

## Current state and next actions

The local OneDrive HTML and the project's `website/index.html` have the
Supabase Edge Function URL and required publishable `apikey` headers for member
login, data, export, and sign-out. The deploy-ready static files are in
`website-build`. The Edge Function and migration are present in this ERP source
tree. The remote
migration and function still need to be applied/deployed, and the GitHub source
repository must be connected to Netlify for the public hosting change to go
live. The current ERP checkout has no configured Git remote and this computer
does not have the Supabase CLI installed, so those account/repository steps
cannot be completed from this checkout yet.
