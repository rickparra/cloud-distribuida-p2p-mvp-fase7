"""Manual demo decision for a pending provider node. No real attestation."""

from __future__ import annotations

import getpass
import os

from app import connection
from launch import load_dotenv


load_dotenv()


def main():
    if not os.environ.get("ORACLE_USER"):
        os.environ["ORACLE_USER"] = input("Usuario/RM Oracle: ").strip()
    if not os.environ.get("ORACLE_PASSWORD"):
        os.environ["ORACLE_PASSWORD"] = getpass.getpass("Senha Oracle: ")
    os.environ.setdefault("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL")
    code = input("Codigo do no pendente: ").strip().upper()
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT NODE_CODE, OPERATOR_NAME, OPERATOR_CNPJ, OPERATOR_UF,
                      GUARANTEE_BRL, TEE_ENABLED, LOCAL_PERSISTENCE, APPROVED
                 FROM F6POC_NODES WHERE NODE_CODE=:code""",
            {"code": code},
        )
        row = cur.fetchone()
        if row is None:
            raise SystemExit("No nao encontrado.")
        print("\nRegistro de demonstracao:")
        for label, value in zip(("No", "Operador", "CNPJ", "UF", "Garantia declarada",
                                 "TEE declarado", "Persistencia declarada", "Aprovado"), row):
            print(f"{label}: {value}")
        if row[-1] == 1:
            print("O no ja esta marcado como aprovado no catalogo.")
            return
        print("ATENCAO: este comando registra somente uma decisao manual de demonstracao.")
        print("Ele nao verifica CNPJ, deposito, local fisico, TEE nem efemeridade.")
        if input("Digite APROVAR DEMO para continuar: ").strip() != "APROVAR DEMO":
            print("Sem alteracao.")
            return
        cur.execute("UPDATE F6POC_NODES SET APPROVED=1 WHERE NODE_CODE=:code AND APPROVED=0", {"code": code})
        conn.commit()
        print("No marcado como aprovado no catalogo de demonstracao.")


if __name__ == "__main__":
    main()
