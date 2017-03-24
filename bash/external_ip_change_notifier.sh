#!/bin/bash

# IP Log File
LASTFILE="/root/.lastip"

# Logging Function
log () {
    NOW=$(date +"%x %X")
    echo "[$NOW] $1"
}

# Fetch IP
IP=$(curl -4 -s myip.ipip.net | awk '{print $2}' | sed 's/IP：//')
if [ ! -f $LASTFILE ]; then
    log "LAST IP Record Not Found, Creating New Record..."
    echo $IP > $LASTFILE
fi
LASTIP=$(cat $LASTFILE)

# Server Configuration
SMTP_SERVER="Your_SMTP_SERVER_IP_OR_DOMAIN"
SMTP_PORT="Your_SMTP_SERVER_PORT"
SMTP_USER="Your_SMTP_SERVER_USER"
SMTP_PW=$(echo 'Your_Password_Hash' | openssl enc -aes-256-cbc -a -d -salt -pass pass:notifier)
IFTLS="no" # Get your hash with: "echo your_password | openssl enc -aes-256-cbc -a -salt -pass pass:notifier"

# Mail Configuration
SENDER_MAIL="$SMTP_USER"
RECIEVER_MAIL="$SMTP_USER;RECIEVER2;RECIEVER3"
MAIL_SUBJECT="[Caution] Your_External_IP Changed!"
MAIL_CONTENT="Your_External_IP has changed to $IP"

# Check IP Changes
checkip () {
    if [ "$LASTIP" != "$IP" ]; then
        log "IP changed to $IP"
        log "Sending mail to $RECIEVER_MAIL..."
        doaction=$(sendemail -s $SMTP_SERVER:$SMTP_PORT -o username=$SMTP_USER -o password=$SMTP_PW -o tls=$IFTLS -f $SENDER_MAIL -t $RECIEVER_MAIL -u $MAIL_SUBJECT -m $MAIL_CONTENT)
        log "$doaction"
        echo "$IP" > "$LASTFILE"
    else
        log "IP Unchanged. Skipping Mail Sending."
    fi
}

# Execute
checkip | tee -a /opt/iplog
