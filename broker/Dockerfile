# Mosquitto for the gateway stack (Broker_Specs §4).
FROM eclipse-mosquitto:2.0.20
RUN apk add --no-cache inotify-tools
COPY entrypoint.sh /usr/local/bin/mc-broker-entrypoint
RUN chmod 755 /usr/local/bin/mc-broker-entrypoint
USER mosquitto
ENTRYPOINT ["/usr/local/bin/mc-broker-entrypoint"]
