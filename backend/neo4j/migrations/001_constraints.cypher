CREATE CONSTRAINT truck_unit IF NOT EXISTS FOR (t:Truck) REQUIRE (t.tenant_id, t.unit_number) IS UNIQUE;
CREATE CONSTRAINT truck_vin IF NOT EXISTS FOR (t:Truck) REQUIRE (t.tenant_id, t.vin) IS UNIQUE;
CREATE CONSTRAINT driver_license IF NOT EXISTS FOR (d:Driver) REQUIRE (d.tenant_id, d.license_number) IS UNIQUE;
CREATE CONSTRAINT vendor_name_addr IF NOT EXISTS FOR (v:Vendor) REQUIRE (v.tenant_id, v.name, v.address) IS UNIQUE;

CREATE INDEX truck_pg_id IF NOT EXISTS FOR (t:Truck) ON (t.pg_id);
CREATE INDEX truck_unit_number IF NOT EXISTS FOR (t:Truck) ON (t.unit_number);
CREATE INDEX truck_vin IF NOT EXISTS FOR (t:Truck) ON (t.vin);

CREATE INDEX driver_pg_id IF NOT EXISTS FOR (d:Driver) ON (d.pg_id);
CREATE INDEX driver_license_number IF NOT EXISTS FOR (d:Driver) ON (d.license_number);

CREATE INDEX vendor_pg_id IF NOT EXISTS FOR (v:Vendor) ON (v.pg_id);

CREATE INDEX trailer_pg_id IF NOT EXISTS FOR (t:Trailer) ON (t.pg_id);

CREATE INDEX document_pg_id IF NOT EXISTS FOR (d:Document) ON (d.pg_id);

CREATE INDEX insurance_policy_pg_id IF NOT EXISTS FOR (p:InsurancePolicy) ON (p.pg_id);
CREATE INDEX insurance_policy_number IF NOT EXISTS FOR (p:InsurancePolicy) ON (p.policy_number);

CREATE INDEX ifta_filing_pg_id IF NOT EXISTS FOR (f:IFTAFiling) ON (f.pg_id);
CREATE INDEX ifta_filing_quarter IF NOT EXISTS FOR (f:IFTAFiling) ON (f.quarter);
