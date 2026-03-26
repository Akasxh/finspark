-- Runs once when the Postgres container is first created.
CREATE DATABASE finspark_test
    WITH OWNER = finspark
    ENCODING = 'UTF8'
    TEMPLATE = template0;

GRANT ALL PRIVILEGES ON DATABASE finspark_test TO finspark;
