FROM postgres:15

# Custom configuration can be added here if needed
COPY postgresql.conf /etc/postgresql/postgresql.conf

EXPOSE 5432 