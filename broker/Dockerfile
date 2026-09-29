# Same image for the cloud broker and the hub broker; the mounted
# mosquitto.conf decides the role (Broker_Specs §5).
FROM eclipse-mosquitto:2.0.20
RUN apk add --no-cache inotify-tools
COPY entrypoint.sh /usr/local/bin/mc-broker-entrypoint
RUN chmod 755 /usr/local/bin/mc-broker-entrypoint
USER mosquitto
ENTRYPOINT ["/usr/local/bin/mc-broker-entrypoint"]
