
CREATE TABLE ecmapp.no_data_report (
	aircraft_id text NULL,
	flight_phase text NULL,
	last_seen_flight_datetime timestamptz NULL
);

-- pivot scripts for each type and engine id merging can be found in /Users/bogdan-korzh/ecm/scripts

CREATE TABLE s7_mdb.aircraft_input (
	aircraft_id varchar(16) NOT NULL,
	flight_phase varchar(32) NOT NULL,
	flight_datetime timestamp NOT NULL,
	parameter_name varchar(16) NOT NULL,
	integer_value int8 NULL,
	float_value float8 NULL,
	char_value varchar(32) NULL
);
CREATE INDEX test_idx4 ON s7_mdb.aircraft_input USING btree (aircraft_id, flight_datetime);

CREATE TABLE s7_mdb.engine_raw_output (
	aircraft_id varchar(16) NOT NULL,
	engine_position int4 NOT NULL,
	flight_phase varchar(32) NOT NULL,
	flight_datetime timestamp NOT NULL,
	parameter_name varchar(16) NOT NULL,
	integer_value int8 NULL,
	float_value float8 NULL,
	char_value varchar(32) NULL
);
CREATE INDEX test_idx1 ON s7_mdb.engine_raw_output USING btree (aircraft_id, flight_datetime);


CREATE TABLE s7_mdb.engine_input (
	aircraft_id varchar(16) NOT NULL,
	engine_position int4 NOT NULL,
	flight_phase varchar(32) NOT NULL,
	flight_datetime timestamp NOT NULL,
	parameter_name varchar(16) NOT NULL,
	integer_value int8 NULL,
	float_value float8 NULL,
	char_value varchar(32) NULL
);
CREATE INDEX test_idx3 ON s7_mdb.engine_input USING btree (aircraft_id, flight_datetime);


CREATE TABLE s7_mdb.onwing_engine (
	aircraft_id varchar(16) NOT NULL,
	engine_position int4 NOT NULL,
	install_datetime timestamp NOT NULL,
	engine_id varchar(24) NOT NULL,
	aircraft_family varchar(40) NOT NULL,
	engine_family varchar(40) NOT NULL,
	thrust_rating float8 NULL,
	removal_datetime timestamp NULL,
	hrs_at_install int8 NULL,
	cyc_at_install int8 NULL,
	hrs_at_removal int8 NULL,
	cyc_at_removal int8 NULL,
	number_removals int8 NOT NULL,
	number_shop_visits int8 NULL,
	deletion_flag varchar(6) NULL,
	reason_for_removal varchar(60) NULL
);
CREATE INDEX test_idx2 ON s7_mdb.onwing_engine USING btree (aircraft_id);
