# Linkr staging runbook

Staging is ephemeral. It is built at the start of a session and destroyed at the
end. Nothing here is long lived, so there is no backup step and no data to
preserve.

All timings below were measured on 2026-11-24 against a `t3.micro` in
`us-east-1`. They are real numbers from a real drill, not estimates.

| Operation | Time | Notes |
|---|---|---|
| Deploy a new image | **21s** | 15.8s of that is the image pull from GHCR |
| Roll back to the previous image | **6s** | No pull. The image is already on the host |
| Build the environment from nothing | ~90s | `terraform apply`, before host setup |
| Destroy the environment | ~60s | See section 6, and read the warning |

**Rolling back is about three and a half times faster than rolling forward, and
the whole difference is that the artifact already exists.** When someone during
an incident says they can patch it in ten minutes, that is the number to answer
with. Go back first. Debug in daylight.

---

## 0. Pre-flight. Check your IP.

The security group allows port 8000 from exactly one address. Home broadband
rotates that address without telling you.

```bash
cd project/infra
sed -i "s|^operator_ip_cidr.*|operator_ip_cidr = \"$(curl -s https://checkip.amazonaws.com)/32\"|" terraform.tfvars
cat terraform.tfvars
```

Do this first, every single time. It has caught a stale address twice.

`terraform plan` will not catch it for you. Terraform compares your code against
reality. It has no way of knowing that your code is wrong. A stale allowlist
produces a plan that says `No changes`, an apply that goes green, and an
application that refuses every connection you make.

---

## 1. Build the environment

```bash
cd project/infra
terraform plan -out=tfplan
```

Read the summary line before applying.

* **7 to add** is correct for a clean build.
* **8 to add**, or 8 to destroy later, means the monthly budget is in scope.
  Stop and read section 6.

```bash
terraform apply tfplan
```

The output gives you `staging_public_ip`. Every check below uses it.

A saved plan is a snapshot of a decision, not a set of instructions. It already
has your variable values baked in. If you change `terraform.tfvars` after saving
a plan, you must plan again. Applying the old file applies the old values.

---

## 2. Set up the host

Connect through Session Manager. EC2 console, Instances, select
`linkr-staging`, Connect, Session Manager tab, Connect. There is no SSH key and
no port 22 rule, by design.

Confirm you are actually on the instance before typing anything else.

```bash
whoami && head -2 /etc/os-release
```

You want `ssm-user` and Amazon Linux. If it shows your laptop username, you are
typing in the wrong window.

```bash
cd ~
```

Session Manager starts you in `/usr/bin`, which you cannot write to. Everything
below fails with `Permission denied` if you skip this.

```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ssm-user
newgrp docker
```

`enable --now` does two jobs. It starts Docker now, and it makes Docker start on
boot. `usermod -aG` must keep the `-a`. Without it, `-G` replaces every group
you belong to instead of adding one.

`newgrp` replaces your shell rather than returning to it, so anything chained
after it with `&&` is silently discarded. Put it on its own line.

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -sSL https://github.com/docker/compose/releases/download/v5.7.1/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
```

The version is pinned. Never `latest`. An environment you cannot rebuild
identically is not an environment, it is a coincidence.

---

## 3. Deploy

```bash
git clone https://github.com/Alfred-Omosona/linkr-platform.git
cd linkr-platform
```

Write the environment file. Replace the two placeholders.

```bash
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 16)
LINKR_IMAGE_TAG=SHA_TO_DEPLOY
LINKR_BASE_URL=http://STAGING_PUBLIC_IP:8000
EOF
cat .env
```

Use `<<EOF`, not `<<'EOF'`. Unquoted, bash expands `$(openssl rand -hex 16)` and
writes a random password. Quoted, it writes that text into the file literally,
Postgres accepts it as a password, and you never find out.

Always `cat .env` afterwards and look at what you actually wrote.

```bash
START=$(date +%s)
docker compose -f compose.staging.yaml up -d
until curl -sf localhost:8000/health | grep -q 'SHA_TO_DEPLOY'; do sleep 1; done
echo "DEPLOY TOOK $(( $(date +%s) - START ))s"
```

Nothing is built here. `compose.staging.yaml` has no `build:` key. It runs the
image CI built, scanned and pushed. If that file ever grows a `build:` key, the
thing running in staging stops being the thing CI tested.

The `until` loop is the point of this block. It does not wait a fixed number of
seconds, and it does not trust the exit code of `up -d`. It waits until the
running application reports the specific commit you asked for. The clock stops
when reality changed, not when the command returned.

---

## 4. Verify. Three checks, from your laptop.

Run these from outside, not on the box. They have to pass through the security
group the way a real user does.

```bash
BASE=http://STAGING_PUBLIC_IP:8000

curl -sS $BASE/health; echo
curl -sS -o /dev/null -w "ready: HTTP %{http_code}\n" $BASE/ready
CODE=$(curl -sS -X POST $BASE/api/links -H 'content-type: application/json' \
  -d '{"url":"https://example.com"}' | grep -o '"code":"[^"]*"' | cut -d'"' -f4)
curl -sS -o /dev/null -w "redirect: HTTP %{http_code} -> %{redirect_url}\n" $BASE/$CODE
curl -sS $BASE/api/links/$CODE; echo
```

| Check | Expected | What it proves |
|---|---|---|
| `/health` | 200, and `git_sha` equal to the tag you deployed | The build you think you deployed is the one running. Nothing else catches a deploy that fails while looking successful |
| `/ready` | HTTP 200 | The application can reach its database |
| POST, redirect, hits | 201, then 307 to the target, then `hits` incremented | The product works end to end |

Three checks, because each one passes while the others fail. On 2026-11-22 the
database was stopped and `/health` stayed at 200 for the whole outage. A single
"is it up" check would have called that healthy.

Use `curl -sS`, not `-s`. Capital S keeps errors visible while still hiding the
progress bar. With `-s` alone, a failure prints nothing at all.

If curl returns exit code `000`, that is not a crash. It means no HTTP response
arrived. Check the allowlist in section 0 first.

---

## 5. Roll back

A rollback is not a rebuild. It points the host at an image that already exists,
was already scanned, and already passed CI.

Rebuilding the old commit does not give you the old image. It gives you a new
one wearing the old commit's name. The base image has moved, unpinned packages
resolve to today's versions, and the result has never been tested. You would be
introducing an untested artifact at the worst possible moment.

```bash
START=$(date +%s)
sed -i 's/^LINKR_IMAGE_TAG=.*/LINKR_IMAGE_TAG=PREVIOUS_SHA/' .env
docker compose -f compose.staging.yaml up -d
until curl -sf localhost:8000/health | grep -q 'PREVIOUS_SHA'; do sleep 1; done
echo "ROLLBACK TOOK $(( $(date +%s) - START ))s"
```

Then re-run every check in section 4. Verification works in both directions. It
is not enough that the box is answering. The build that was bad must be gone,
and the build that was good must be back.

**Measured on 2026-11-24: 6 seconds.** No image pull, because the previous image
was still in the host cache from earlier the same session. A rollback after a
host rebuild would include a pull and land closer to 20 seconds.

---

## 6. Destroy

### Read this before you type anything

The account level monthly budget lives in the same Terraform state as staging.
It is not part of staging. It is the cost guardrail that tells you when the bill
is running away.

**A plain `terraform destroy` will take it with everything else.** On 2026-11-22
a destroy plan showed 8 resources instead of 7, and that is exactly what it was
about to do. Losing your cost alarm at the moment you stop watching the account
is the worst possible time to lose it.

Until the budget is moved into its own state, destroy by explicit target.

```bash
cd project/infra
terraform plan -destroy
```

If that shows 8, the budget is in scope. Do not apply it. Use the targeted
destroy below.

```bash
terraform destroy \
  -target=aws_instance.linkr_staging \
  -target=aws_vpc_security_group_ingress_rule.api_from_operator \
  -target=aws_vpc_security_group_egress_rule.all_outbound \
  -target=aws_security_group.linkr_staging \
  -target=aws_iam_instance_profile.linkr_staging \
  -target=aws_iam_role_policy_attachment.ssm_core \
  -target=aws_iam_role.linkr_staging
```

Confirm the prompt says **7 to destroy** before typing `yes`.

### Verify at the source, not by exit code

`Destroy complete!` means Terraform finished. It does not mean the resources are
gone, and a destroy that fails halfway while leaving billable resources behind
is itself a cost incident.

Ask AWS directly, and check both directions.

```bash
aws ec2 describe-instances \
  --filters "Name=tag:project,Values=linkr" \
  --query "Reservations[].Instances[].{id:InstanceId,state:State.Name}" --output table
```

```bash
aws budgets describe-budgets \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --query "Budgets[].BudgetName"
```

The instance must read `terminated`, or be absent. The budget **must still be
there**. One command proves the thing you wanted gone has gone. The other proves
the thing you wanted kept survived. A teardown that only checks the first half
is how you discover in January that the guardrail went in November.

---

## Known gaps

* The budget shares a state file with staging. Splitting it out removes the need
  for the targeted destroy in section 6. Tracked for Stage 2.
* Host setup in section 2 is manual. It is the same commands every time, so it
  is a user-data script waiting to happen.
* `compose.monitoring.yaml` is not yet started on staging. The cadvisor panel
  cannot work on Docker Desktop under WSL, where cadvisor reads the virtual
  machine's systemd units rather than container metadata. It needs a real Linux
  host, which this box is.
