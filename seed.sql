MERGE INTO F6POC_NODES n
USING (SELECT 'BR-TEE-01' code, 'No Brasil com TEE' label, 'BR' country, 1 tee, 0 persist, 1 approved, 128 capacity, 0.50 rate FROM dual) s
ON (n.NODE_CODE = s.code)
WHEN NOT MATCHED THEN INSERT (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,PRICE_PER_VCPU_HOUR) VALUES (s.code,s.label,s.country,s.tee,s.persist,s.approved,s.capacity,s.rate)
-- @statement
UPDATE F6POC_NODES SET OPERATOR_CNPJ='12345678000190', OPERATOR_NAME='Datacenter Sul Infraestrutura Ltda', OPERATOR_UF='RS', GUARANTEE_BRL=50000
WHERE NODE_CODE='BR-TEE-01' AND OPERATOR_CNPJ IS NULL
-- @statement
MERGE INTO F6POC_NODES n
USING (SELECT 'BR-SEM-TEE' code, 'No Brasil sem TEE' label, 'BR' country, 0 tee, 0 persist, 1 approved, 128 capacity, 0.22 rate FROM dual) s
ON (n.NODE_CODE = s.code)
WHEN NOT MATCHED THEN INSERT (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,PRICE_PER_VCPU_HOUR) VALUES (s.code,s.label,s.country,s.tee,s.persist,s.approved,s.capacity,s.rate)
-- @statement
UPDATE F6POC_NODES SET OPERATOR_CNPJ='34567890000172', OPERATOR_NAME='HPC Campinas Servicos de Computacao', OPERATOR_UF='SP', GUARANTEE_BRL=80000
WHERE NODE_CODE='BR-SEM-TEE' AND OPERATOR_CNPJ IS NULL
-- @statement
MERGE INTO F6POC_NODES n
USING (SELECT 'EXT-TEE-01' code, 'No fora do Brasil com TEE' label, 'US' country, 1 tee, 0 persist, 1 approved, 128 capacity, 0.12 rate FROM dual) s
ON (n.NODE_CODE = s.code)
WHEN NOT MATCHED THEN INSERT (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,PRICE_PER_VCPU_HOUR) VALUES (s.code,s.label,s.country,s.tee,s.persist,s.approved,s.capacity,s.rate)
-- @statement
UPDATE F6POC_NODES SET OPERATOR_CNPJ='56789012000154', OPERATOR_NAME='Global Edge Compute do Brasil Ltda', OPERATOR_UF='SP', GUARANTEE_BRL=45000
WHERE NODE_CODE='EXT-TEE-01' AND OPERATOR_CNPJ IS NULL
-- @statement
MERGE INTO F6POC_NODES n
USING (SELECT 'BR-PERSIST-01' code, 'No Brasil com persistencia local' label, 'BR' country, 1 tee, 1 persist, 1 approved, 128 capacity, 0.16 rate FROM dual) s
ON (n.NODE_CODE = s.code)
WHEN NOT MATCHED THEN INSERT (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,PRICE_PER_VCPU_HOUR) VALUES (s.code,s.label,s.country,s.tee,s.persist,s.approved,s.capacity,s.rate)
-- @statement
UPDATE F6POC_NODES SET OPERATOR_CNPJ='23456789000181', OPERATOR_NAME='Nuvem Regional Nordeste S.A.', OPERATOR_UF='PE', GUARANTEE_BRL=35000
WHERE NODE_CODE='BR-PERSIST-01' AND OPERATOR_CNPJ IS NULL
-- @statement
MERGE INTO F6POC_NODES n
USING (SELECT 'BR-TEE-02' code, 'Segundo executor Brasil com TEE declarado' label, 'BR' country, 1 tee, 0 persist, 1 approved, 64 capacity, 0.55 rate FROM dual) s
ON (n.NODE_CODE = s.code)
WHEN NOT MATCHED THEN INSERT (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,PRICE_PER_VCPU_HOUR) VALUES (s.code,s.label,s.country,s.tee,s.persist,s.approved,s.capacity,s.rate)
-- @statement
UPDATE F6POC_NODES SET OPERATOR_CNPJ='23456789000181', OPERATOR_NAME='Nuvem Regional Nordeste S.A.', OPERATOR_UF='PE', GUARANTEE_BRL=35000
WHERE NODE_CODE='BR-TEE-02' AND OPERATOR_CNPJ IS NULL
