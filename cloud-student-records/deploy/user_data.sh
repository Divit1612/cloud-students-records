#!/bin/bash
# =============================================================================
# EC2 Launch Template User Data - Amazon Linux 2023
# Student Record Management System (Flask + Gunicorn + Nginx + DynamoDB)
#
# >>> CHANGE THESE TWO PLACEHOLDERS BEFORE PASTING INTO THE LAUNCH TEMPLATE <<<
#   REPO_URL   : HTTPS URL of YOUR public GitHub repository
#   AWS_REGION : Region where you created the StudentRecords DynamoDB table
# =============================================================================
REPO_URL="https://github.com/YOUR_USERNAME/cloud-student-records.git"   # <-- CHANGE
AWS_REGION="ap-south-1"                                                  # <-- CHANGE if needed

# Fixed settings (normally no change needed)
DYNAMODB_TABLE_NAME="StudentRecords"
APP_DIR="/opt/student-record-app"
APP_USER="studentapp"
LOG_FILE="/var/log/student-app-userdata.log"

set -euxo pipefail
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== User data started: $(date -u) ==="

# 1. Install packages (non-interactive)
dnf -y update
dnf -y install python3 python3-pip git nginx

# 2. Create an unprivileged service user
id -u "$APP_USER" &>/dev/null || useradd --system --shell /sbin/nologin "$APP_USER"

# 3. Clone the application (fresh copy on every new instance)
rm -rf "$APP_DIR"
GIT_TERMINAL_PROMPT=0 git clone --depth 1 "$REPO_URL" "$APP_DIR"

# Support repos where the app lives in a "cloud-student-records" subfolder
if [ ! -f "$APP_DIR/app.py" ] && [ -f "$APP_DIR/cloud-student-records/app.py" ]; then
    APP_SRC="$APP_DIR/cloud-student-records"
else
    APP_SRC="$APP_DIR"
fi

# 4. Virtual environment + dependencies
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_SRC/requirements.txt"
"$APP_DIR/.venv/bin/pip" install gunicorn

# 5. Environment file (no AWS keys - credentials come from the IAM role)
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
cat > /etc/student-app.env <<EOF
STORAGE_BACKEND=dynamodb
DYNAMODB_TABLE_NAME=${DYNAMODB_TABLE_NAME}
AWS_DEFAULT_REGION=${AWS_REGION}
AWS_REGION=${AWS_REGION}
SECRET_KEY=${SECRET_KEY}
LOG_LEVEL=INFO
EOF
chmod 640 /etc/student-app.env
chown root:"$APP_USER" /etc/student-app.env
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# 6. systemd service: student-app
cat > /etc/systemd/system/student-app.service <<EOF
[Unit]
Description=Student Record Management System (Gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_SRC}
EnvironmentFile=/etc/student-app.env
ExecStart=${APP_DIR}/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 7. Nginx reverse proxy: port 80 -> 127.0.0.1:8000
cat > /etc/nginx/conf.d/student-app.conf <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF
# Disable the default server block in nginx.conf so ours handles port 80
sed -i -E 's/listen([[:space:]]+)80;/listen\18081;/; s/listen([[:space:]]+)\[::\]:80;/listen\1[::]:8081;/' /etc/nginx/nginx.conf || true
nginx -t

# 8. Enable and start services
systemctl daemon-reload
systemctl enable --now student-app
systemctl enable --now nginx
systemctl restart nginx

# 9. Quick local health check
sleep 5
curl -fsS http://127.0.0.1/health || echo "WARNING: health check failed - see journalctl -u student-app"

echo "=== User data finished: $(date -u) ==="
