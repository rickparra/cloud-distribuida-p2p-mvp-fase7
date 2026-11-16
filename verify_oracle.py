"""Prompt for Oracle credentials and run the schema smoke tests."""

from __future__ import annotations

import getpass
import os

from app import connection
from launch import load_dotenv
from smoke_oracle import run


if __name__ == "__main__":
    load_dotenv()
    if not os.environ.get("ORACLE_USER"):
        os.environ["ORACLE_USER"] = input("Usuario/RM Oracle: ").strip()
    if not os.environ.get("ORACLE_PASSWORD"):
        os.environ["ORACLE_PASSWORD"] = getpass.getpass("Senha Oracle: ")
    os.environ.setdefault("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL")
    run()
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN RESULT_SHA256 IS NOT NULL THEN 1 ELSE 0 END) FROM F7MVP_EXECUTIONS")
        tasks, completed = cur.fetchone()
        print(f"PASS: tabela de execucoes do MVP acessivel; {tasks} tarefas, {completed or 0} hashes de resultado persistidos.")
        cur.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME='F7MVP_EXECUTIONS'")
        columns = {row[0] for row in cur.fetchall()}
        if {"INPUT_JSON", "RESULT_JSON"} & columns:
            raise AssertionError("O schema ainda contem colunas de dado bruto do cliente.")
        if not {"INPUT_SHA256", "RESULT_SHA256", "INPUT_COUNT"}.issubset(columns):
            raise AssertionError("Faltam colunas de prova por hash.")
        print("PASS: Oracle guarda hashes e metadados, sem colunas de entrada/resultado bruto.")
        cur.execute("SELECT COUNT(*) FROM F7MVP_SETTLEMENTS WHERE GROSS_BRL <> PLATFORM_FEE_BRL + PROVIDER_BRL")
        if cur.fetchone()[0]:
            raise AssertionError("Ledger financeiro demonstrativo desbalanceado.")
        print("PASS: ledger financeiro demonstrativo balanceado.")
        cur.execute("""SELECT COUNT(*) FROM F7MVP_HOSTING h
                       JOIN F6POC_LEASES l ON l.LEASE_ID=h.LEASE_ID
                      WHERE (h.STATUS='ACTIVE' AND l.STATUS<>'AUTHORIZED')
                         OR (h.STATUS='EXPIRED' AND l.STATUS<>'COMPLETED')
                         OR (h.STATUS='CANCELLED' AND l.STATUS<>'FAILED')""")
        if cur.fetchone()[0]:
            raise AssertionError("Estado de hospedagem diverge do lease Oracle.")
        print("PASS: estados da hospedagem e dos leases Oracle consistentes.")
        cur.execute("""SELECT COUNT(*) FROM (
                         SELECT h.GROUP_TOKEN, COUNT(*) AS N,
                                COUNT(DISTINCT l.NODE_CODE) AS NODES
                           FROM F7MVP_HOSTING h
                           JOIN F6POC_LEASES l ON l.LEASE_ID=h.LEASE_ID
                          WHERE h.GROUP_TOKEN IS NOT NULL
                          GROUP BY h.GROUP_TOKEN
                         HAVING COUNT(*) <> 2 OR COUNT(DISTINCT l.NODE_CODE) <> 2
                       )""")
        if cur.fetchone()[0]:
            raise AssertionError("Um grupo de hospedagem nao possui dois nos distintos.")
        print("PASS: cada grupo de hospedagem possui dois leases em nos distintos.")
