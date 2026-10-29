# Databricks notebook source
# MAGIC %sql
# MAGIC UPDATE `dbdemos2`.`test_schema_hp`.`invoices`
# MAGIC SET bill_date = '2024-12-10'
# MAGIC WHERE bill_date IS NULL;
# MAGIC
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from `dbdemos2`.`test_schema_hp`.`invoices`