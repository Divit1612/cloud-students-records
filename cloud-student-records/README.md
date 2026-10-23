# Student Record Management System on AWS
### EC2 · DynamoDB · CloudWatch · EC2 Auto Scaling · Launch Template

## 1. Introduction
A Flask web application to add, list, edit and delete student records. It runs
locally on Windows with **SQLite** and on **Amazon EC2** (Amazon Linux 2023) with
**DynamoDB**, behind **Nginx + Gunicorn**, launched by an **Auto Scaling Group**
from a **Launch Template**, monitored with **CloudWatch**.

## 2. Features
- Add / list / edit / delete students (ID = UUID, name, email, course, created time)
- Success/error flash messages, friendly empty state, responsive UI
- Server-side validation; safe error pages (no stack traces / config shown)
- `/health` endpoint → HTTP 200 `{"status":"ok"}`
- Two explicit storage modes: `STORAGE_BACKEND=sqlite` or `dynamodb`
  (no silent fallback — DynamoDB errors are logged and a safe message is shown)
- No credentials in code: EC2 uses an IAM role via Boto3's default credential chain

## 3. Architecture
```
 Browser ──HTTP:80──► EC2 (public subnet, Amazon Linux 2023)
                       Nginx :80 ─► Gunicorn 127.0.0.1:8000 ─► Flask (app:app)
                                                            │ boto3 (IAM role creds)
                                                            ▼
                                                   DynamoDB: StudentRecords
 Auto Scaling Group (min 1 / desired 1 / max 2) ◄── Launch Template (AMI, SG, IAM profile, User Data)
        ▲
 CloudWatch CPUUtilization ── target tracking 50% ── alarms (managed by AWS)
```
No load balancer is used (to avoid cost). Each instance has its own public IP.

## 4. File structure
```
cloud-student-records/
├── app.py                 Flask app (routes, validation, error handlers)
├── storage.py             SQLiteStorage + DynamoDBStorage + get_storage()
├── requirements.txt
├── .env.example           Example config (no secrets)
├── .gitignore             Excludes .venv, .env, .data, keys
├── .gitattributes         Forces LF endings for *.sh (CRLF breaks bash on EC2)
├── README.md
├── templates/index.html   Main page
├── templates/error.html   Safe error page (extra: used by 404/405/500 handlers)
├── static/style.css
├── deploy/user_data.sh    Launch Template User Data
├── deploy/iam_policy.json Least-privilege IAM policy (extra: copy/paste in IAM)
├── tests/test_app.py      Pytest suite (temporary SQLite DB)
└── docs/SCREENSHOT_CHECKLIST.md
```

## 5. Prerequisites
- Windows 10/11, Python 3.10+ (`py --version`), Git, a GitHub account
- An AWS account with Console access (Free Tier eligible where possible)

## 6. Windows setup and local run
```powershell
cd cloud-student-records
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env      # optional; sqlite is the default
python app.py
```
Open **http://127.0.0.1:5000**. Data is stored in `.data\students.db`.

**If PowerShell blocks activation** ("running scripts is disabled"):
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process   # current window only
.\.venv\Scripts\Activate.ps1
```
Or skip activation entirely: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
then `.\.venv\Scripts\python.exe app.py`.

> Gunicorn does not run on Windows; it is installed only on Linux (EC2).

## 7. Local testing
Automated (uses a temporary SQLite DB, never touches `.data`):
```powershell
python -m pytest -v
```
Manual: add a student → see "added successfully"; click **Edit**, change course →
"updated successfully"; **Delete** → "deleted"; delete all → empty state;
open http://127.0.0.1:5000/health → `{"status":"ok"}`. Submit an invalid email
to see validation errors.

## 8. GitHub repository setup
Create an **empty public** repo named `cloud-student-records` on GitHub (no README), then:
```powershell
cd cloud-student-records
git init
git add .
git status            # confirm .env, .venv and .data are NOT listed
git commit -m "Student Record Management System"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cloud-student-records.git
git push -u origin main
```
The repository root must contain `app.py` (the script also supports a
`cloud-student-records/` subfolder).

## 9. AWS region
Pick one region and use it for **everything** (table, IAM policy ARN, EC2, ASG,
User Data). This guide uses **Asia Pacific (Mumbai) `ap-south-1`**. Select it in
the top-right region menu of the Console.

## 10. DynamoDB table
DynamoDB → **Create table**
- Table name: `StudentRecords`
- Partition key: `student_id` — **String**
- No sort key · Table settings: **Default settings** (or Customize → On-demand)
- **Create table**, wait for status *Active*.

## 11. IAM policy and EC2 role
1. Note your 12-digit Account ID (top-right menu).
2. IAM → Policies → **Create policy** → JSON. Paste [deploy/iam_policy.json](deploy/iam_policy.json),
   replacing `YOUR_ACCOUNT_ID` (and region if not `ap-south-1`).
   Name: `StudentRecordsDynamoDBPolicy` → Create.
3. IAM → Roles → **Create role** → Trusted entity: *AWS service* → Use case: **EC2**.
4. Attach `StudentRecordsDynamoDBPolicy`. Role name: `StudentAppEC2Role` → Create.
   (The console automatically creates an instance profile with the same name.)

Allowed actions: `DescribeTable, PutItem, GetItem, UpdateItem, DeleteItem, Scan` on that table only.

## 12. Security group
EC2 → Security Groups → **Create** · Name `student-app-sg` · default VPC
| Type | Port | Source | Purpose |
|------|------|--------|---------|
| HTTP | 80 | 0.0.0.0/0 | Public demo site |
| SSH | 22 | **My IP** | Admin access |
Outbound: keep default (all traffic). Ports **5000** (local dev) and **8000**
(Gunicorn, bound to 127.0.0.1) must **not** be opened — Nginx proxies to them internally.

The instance must be in a **public subnet** (route to an Internet Gateway) with
a **public IPv4 address**, so it can reach GitHub, dnf repos and DynamoDB and so
you can browse to it. The default VPC subnets satisfy this.

## 13. Launch Template
**Before:** edit `deploy/user_data.sh` lines marked `<-- CHANGE`:
- `REPO_URL="https://github.com/YOUR_USERNAME/cloud-student-records.git"` → your repo URL
- `AWS_REGION="ap-south-1"` → your table's region (keep if Mumbai)

Commit & push that change too (optional), then copy the **whole file content**.

EC2 → Launch Templates → **Create launch template**
- Name: `student-app-lt` · tick *Provide guidance … Auto Scaling*
- AMI: **Amazon Linux 2023 AMI** (64-bit x86)
- Instance type: **t3.micro** (or t2.micro — whichever is Free Tier in your region)
- Key pair: create/select e.g. `student-key` (.pem; keep it private, never commit)
- Network settings: *Don't include subnet*; Security group: `student-app-sg`
- Advanced network configuration → **Auto-assign public IP: Enable**
- Advanced details → **IAM instance profile: `StudentAppEC2Role`**
- Detailed CloudWatch monitoring: **Disable** (basic is free)
- **User data**: paste the edited script → **Create launch template**

## 14. Auto Scaling Group
EC2 → Auto Scaling Groups → **Create**
1. Name `student-asg`, template `student-app-lt` (Latest) → Next
2. VPC: default; Subnets: choose 2+ **public** subnets → Next
3. Load balancing: **No load balancer**; Health checks: EC2; grace period 300 s → Next
4. Group size: **Desired 1, Min 1, Max 2**
5. Scaling: **Target tracking scaling policy** · Name `cpu50` · Metric
   *Average CPU utilization* · Target **50** · Instance warmup **300** seconds → Next
6. Skip notifications, add tag `Name = student-app` → **Create**

AWS automatically creates and manages two CloudWatch alarms for this policy
(`TargetTracking-student-asg-AlarmHigh-…` and `…AlarmLow-…`). Do not edit/delete them.

## 15. Public website testing
Wait ~3–5 minutes. EC2 → Instances → select the `student-app` instance → copy
**Public IPv4 address** → open `http://<public-ip>/` (**http**, not https).
Badge should read **Storage: DynamoDB**. Add a record, then check
DynamoDB → Tables → StudentRecords → **Explore table items** to see it.
Also open `http://<public-ip>/health`.

## 16. CloudWatch
- **Graph:** CloudWatch → Metrics → All metrics → EC2 → *By Auto Scaling Group* →
  `student-asg` CPUUtilization (or *Per-Instance Metrics*). Set period 5 min.
- **Alarms:** CloudWatch → Alarms → All alarms → open the TargetTracking alarms.
  "In alarm" for AlarmLow is normal while CPU is low.
- Basic monitoring sends data every **5 minutes**; graphs may take 10–15 min to appear.
- Optional load test (to see scale-out), on the instance:
  ```bash
  sudo dnf -y install stress-ng
  stress-ng --cpu 2 --timeout 900s
  ```
  Then watch ASG → **Activity** tab (scale-out may take 5–15 minutes).

## 17. Troubleshooting
Connect: EC2 → Instance → **Connect → EC2 Instance Connect**, or
`ssh -i student-key.pem ec2-user@<public-ip>`
```bash
sudo tail -n 100 /var/log/student-app-userdata.log   # our script log
sudo tail -n 100 /var/log/cloud-init-output.log      # cloud-init log
sudo systemctl status student-app nginx
sudo journalctl -u student-app -n 100 --no-pager      # app/Gunicorn logs
curl -i http://127.0.0.1:8000/health                  # Gunicorn direct
curl -i http://127.0.0.1/health                       # via Nginx
sudo nginx -t
cat /etc/student-app.env | grep -v SECRET_KEY
sudo systemctl restart student-app
```
| Symptom | Likely cause |
|---------|-------------|
| Browser timeout | SG missing port 80, no public IP, used https:// |
| 502 Bad Gateway | student-app not running → check journalctl |
| "Could not load student records" | Wrong region/table name or IAM role not attached / policy ARN wrong (`AccessDeniedException` in journalctl) |
| git clone failed | REPO_URL wrong or repo private |
| `$'\r': command not found` | CRLF line endings — keep `.gitattributes`, re-copy script |

User Data only runs at first boot. After fixing the template, create a new
version, set it as default/Latest, then ASG → **Instance refresh** or terminate the instance.

## 18. Cleanup (avoid charges)
1. EC2 → Auto Scaling Groups → `student-asg` → **Delete** (terminates instances, removes policy & its alarms)
2. EC2 → Launch Templates → delete `student-app-lt`
3. DynamoDB → delete table `StudentRecords`
4. EC2 → Security Groups → delete `student-app-sg` (after instances are gone)
5. IAM → delete role `StudentAppEC2Role` and policy `StudentRecordsDynamoDBPolicy`
6. EC2 → Key Pairs → delete `student-key` (optional)
7. CloudWatch → Alarms: confirm no leftover alarms; check **Billing** dashboard.
