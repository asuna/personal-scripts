#!/bin/bash

# IP Log File
LASTFILE="/root/.lastip"

# Logging Function
log () {
    NOW=$(date +"%x %X")
    echo "[$NOW] $1"
}

# Fetch IP
IP=$(curl -4 -s ip.cip.cc)
if [ ! -f $LASTFILE ]; then
    log "LAST IP Record Not Found, Creating New Record..."
    echo $IP > $LASTFILE
fi
LASTIP=$(cat $LASTFILE)

# Server Configuration
SMTP_SERVER="Your_SMTP_SERVER_IP_OR_DOMAIN"
SMTP_PORT="Your_SMTP_SERVER_PORT"
SMTP_USER="Your_SMTP_SERVER_USER"
SMTP_PW=$(echo 'Your_Password_Hash' | openssl enc -aes-256-cbc -a -d -salt -pass pass:notifier) # Get your hash with: "echo your_password | openssl enc -aes-256-cbc -a -salt -pass pass:notifier"， or using cleartext here.
IFTLS="no"

# Mail Configuration
SENDER_MAIL="$SMTP_USER"
RECIEVER_MAIL="$SMTP_USER;RECIEVER2;RECIEVER3"
MAIL_SUBJECT="[Caution] Your_External_IP Changed!"
MAIL_CONTENT="Your_External_IP has changed to $IP, Previous IP is $LASTIP"

# Check IP Changes
checkip () {
    if [ "$LASTIP" != "$IP" ]; then
        log "IP changed to $IP, Previous IP is: $LASTIP"
        log "Sending mail to $RECIEVER_MAIL..."
        doaction=$(sendemail -s $SMTP_SERVER:$SMTP_PORT -o username=$SMTP_USER -o password=$SMTP_PW -o tls=$IFTLS -f $SENDER_MAIL -t $RECIEVER_MAIL -u $MAIL_SUBJECT -m $MAIL_CONTENT)
        log "$doaction"
        echo "$IP" > "$LASTFILE"
    else
        log "IP Unchanged. Skipping Mail Sending."
    fi
}

# Execute
if [[ `wc -l $LASTFILE | awk '{print $1}'` == 1 && `cat $LASTFILE | grep -E '^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$'` ]]; then
    checkip | tee -a /opt/iplog
else
    log "Fetch External IP Failed, trying to refetch..." | tee -a /opt/iplog
    echo $IP > $LASTFILE | tee -a /opt/iplog
fi

exit 0
