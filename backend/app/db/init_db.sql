CREATE USER skillpulse_user WITH PASSWORD 'skillpulse_pass';
CREATE DATABASE skillpulse_db OWNER skillpulse_user;
GRANT ALL PRIVILEGES ON DATABASE skillpulse_db TO skillpulse_user;




/* 
use this command to run this file : 
      psql -U postgres -f backend/db/init_db.sql
*/