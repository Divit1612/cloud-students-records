# Screenshot Checklist

Save screenshots as `docs/screenshots/NN-name.png`. Make sure **no** access keys,
account passwords or private key contents are visible.

| # | Screenshot | Where to capture | Done |
|---|-----------|------------------|------|
| 1 | Application running locally | Browser at `http://127.0.0.1:5000` with a few records + PowerShell showing `python app.py` | ☐ |
| 2 | EC2 instance in **Running** state | EC2 → Instances (instance launched by the ASG, status checks 2/2 passed) | ☐ |
| 3 | Connection/terminal showing deployment | EC2 Instance Connect / SSH: `sudo systemctl status student-app` and `sudo tail -n 30 /var/log/student-app-userdata.log` | ☐ |
| 4 | App opened through EC2 endpoint | Browser at `http://<EC2-public-IPv4>/` showing "Storage: DynamoDB" badge | ☐ |
| 5 | DynamoDB table and sample items | DynamoDB → Tables → StudentRecords → Explore table items | ☐ |
| 6 | CloudWatch metric graph | CloudWatch → Metrics → EC2 → By Auto Scaling Group → CPUUtilization | ☐ |
| 7 | CloudWatch alarm configuration/state | CloudWatch → Alarms → `TargetTracking-student-asg-AlarmHigh-…` / `AlarmLow-…` | ☐ |
| 8 | EC2 Launch Template | EC2 → Launch Templates → `student-app-lt` → details (AMI, type, IAM profile, SG) | ☐ |
| 9 | ASG min / desired / max capacity | EC2 → Auto Scaling Groups → `student-asg` → Details (1 / 1 / 2) | ☐ |
| 10 | Scaling policy and activity/history | ASG → Automatic scaling tab (target 50% CPU) and Activity tab | ☐ |

> Basic monitoring reports EC2 metrics every 5 minutes; wait 10–15 minutes
> after launch before capturing screenshots 6 and 7.
