FROM postgres:16-alpine

RUN apk add --no-cache dcron

COPY backup.sh /backup.sh
RUN chmod +x /backup.sh

COPY crontab /etc/crontabs/root

RUN mkdir -p /backup /var/log

CMD ["crond", "-f", "-l", "2"]
