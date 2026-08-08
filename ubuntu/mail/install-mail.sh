#!/bin/sh
# Почтовый приёмник проекта: Postfix (приём :25) + Dovecot (IMAP :143 на localhost).
# Смысл: почтовый сервер компании пересылает выбранные письма на ai@<MAIL_DOMAIN>,
# они складываются в Maildir пользователя aimail; дальше (отдельная задача)
# OpenClaw читает этот ящик по IMAP и обрабатывает письма.
#
# Запуск ВЛАДЕЛЬЦЕМ (нужен root):
#   sudo sh /srv/1c/ubuntu/mail/install-mail.sh [MAIL_DOMAIN]
# MAIL_DOMAIN по умолчанию: ai.1c.local
#
# Идемпотентно: повторный запуск проверяет состояние, а не делает вслепую.
# Секрет (пароль IMAP) — /etc/1c-mail.env, 640 root:1c-secrets (конвенция проекта).
set -eu

MAIL_DOMAIN="${1:-ai.1c.local}"
MAIL_USER=aimail
ENV_FILE=/etc/1c-mail.env

echo "== пакеты (postfix, dovecot-imapd)"
export DEBIAN_FRONTEND=noninteractive
echo "postfix postfix/main_mailer_type select Local only" | debconf-set-selections
apt-get install -y -q postfix dovecot-imapd

echo "== пользователь $MAIL_USER"
if ! id "$MAIL_USER" >/dev/null 2>&1; then
  useradd -m -s /usr/sbin/nologin "$MAIL_USER"
fi

echo "== секрет $ENV_FILE (создаётся один раз)"
if [ ! -f "$ENV_FILE" ]; then
  PASS="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  printf 'MAIL_USER=%s\nMAIL_PASSWORD=%s\nMAIL_DOMAIN=%s\nMAIL_IMAP=127.0.0.1:143\n' \
    "$MAIL_USER" "$PASS" "$MAIL_DOMAIN" > "$ENV_FILE"
  chown root:1c-secrets "$ENV_FILE" && chmod 640 "$ENV_FILE"
  echo "$MAIL_USER:$PASS" | chpasswd
else
  echo "   уже есть — пароль не трогаем"
fi

echo "== postfix"
postconf -e "mydestination = \$myhostname, localhost.\$mydomain, localhost, $MAIL_DOMAIN"
postconf -e "home_mailbox = Maildir/"
postconf -e "luser_relay = $MAIL_USER"
postconf -e "local_recipient_maps = proxy:unix:passwd.byname \$alias_maps"
if ! grep -q "^ai:[[:space:]]" /etc/aliases; then
  echo "ai: $MAIL_USER" >> /etc/aliases
fi
newaliases

echo "== dovecot (IMAP только localhost, Maildir пользователя)"
cat > /etc/dovecot/conf.d/99-1c-mail.conf << 'EOF'
# Проект 1c: ящик приёмника пересылаемой почты. Ставится ubuntu/mail/install-mail.sh.
mail_location = maildir:~/Maildir
protocols = imap
listen = 127.0.0.1
ssl = no
disable_plaintext_auth = no
EOF

echo "== firewall (только если ufw активен)"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 25/tcp >/dev/null
  echo "   25/tcp открыт"
else
  echo "   ufw не активен — порт 25 и так доступен из сети"
fi

echo "== службы"
systemctl enable --now postfix dovecot >/dev/null
systemctl restart postfix dovecot
systemctl is-active postfix dovecot

echo "== smoke: локальное письмо на ai@$MAIL_DOMAIN"
su -s /bin/sh "$MAIL_USER" -c "echo 'smoke $(date -Is)' | sendmail ai@$MAIL_DOMAIN"
i=0
while [ $i -lt 10 ]; do
  HIT="$(find "/home/$MAIL_USER/Maildir/new" -type f 2>/dev/null | head -1)"
  [ -n "$HIT" ] && break
  i=$((i+1)); sleep 1
done
if [ -n "${HIT:-}" ]; then
  echo "   OK: письмо лежит в $HIT"
else
  echo "   🔴 письмо не появилось за 10 с — смотреть journalctl -u postfix"
  exit 1
fi

echo
echo "Готово. Приём: 25/tcp, адрес ai@$MAIL_DOMAIN (и любой *@$MAIL_DOMAIN — luser_relay)."
echo "Чтение: IMAP 127.0.0.1:143, логин/пароль — $ENV_FILE."
echo "Приёмка целиком — /srv/1c/ubuntu/mail/README.md."
