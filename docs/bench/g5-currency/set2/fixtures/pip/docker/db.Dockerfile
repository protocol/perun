FROM postgres:13.14
COPY init.sql /docker-entrypoint-initdb.d/
