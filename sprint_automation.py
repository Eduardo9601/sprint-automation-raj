"""
Automação de Sprints Semanais - Jira Cloud
Projeto: RAJ | Board ID: 89
Autor: Eduardo André Pedro
---
Este script:
1. Identifica a sprint ativa vencida
2. Cria uma nova sprint com nomenclatura sequencial (Sprint XX - MM/AAAA)
3. Move issues não concluídas da sprint vencida para a nova
4. Fecha a sprint vencida
5. Ativa a nova sprint
"""

import os
import re
import requests
from datetime import datetime, timedelta

# ========== CONFIGURAÇÕES (via variáveis de ambiente) ==========
JIRA_DOMAIN = os.environ["JIRA_DOMAIN"]  # Ex: grazziotin-sa.atlassian.net
JIRA_EMAIL = os.environ["JIRA_EMAIL"]    # Seu email do Jira
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]  # Token gerado no Jira
BOARD_ID = int(os.environ.get("BOARD_ID", "89"))
DURACAO_SPRINT_DIAS = int(os.environ.get("DURACAO_SPRINT_DIAS", "7"))

# ========== CONFIGURAÇÃO DA API ==========
BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def get_sprints(board_id, state):
    """Busca sprints do board por estado (active, future, closed)."""
    url = f"{BASE_URL}/board/{board_id}/sprint"
    params = {"state": state, "maxResults": 50}
    response = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json().get("values", [])


def get_issues_nao_concluidas(sprint_id):
    """Busca issues que NÃO estão com status 'Done' em uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    params = {"maxResults": 200, "fields": "status"}
    response = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
    response.raise_for_status()

    issues = response.json().get("issues", [])
    # Filtra apenas issues que NÃO estão na categoria "done"
    pendentes = [
        issue["key"]
        for issue in issues
        if issue["fields"]["status"]["statusCategory"]["key"] != "done"
    ]
    return pendentes


def extrair_maior_numero_sprint(sprints):
    """Extrai o maior número sequencial das sprints existentes."""
    maior = 0
    for sprint in sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior:
                maior = num
    return maior


def criar_sprint(nome, data_inicio, data_fim, board_id):
    """Cria uma nova sprint no board."""
    url = f"{BASE_URL}/sprint"
    body = {
        "name": nome,
        "startDate": data_inicio,
        "endDate": data_fim,
        "originBoardId": board_id,
        "goal": "Sprint criada automaticamente via GitHub Actions"
    }
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    response.raise_for_status()
    return response.json()


def mover_issues_para_sprint(sprint_id, issue_keys):
    """Move uma lista de issues para a sprint especificada."""
    if not issue_keys:
        print("  Nenhuma issue para mover.")
        return

    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    # A API aceita no máximo 50 issues por vez
    for i in range(0, len(issue_keys), 50):
        batch = issue_keys[i:i+50]
        body = {"issues": batch}
        response = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
        response.raise_for_status()
        print(f"  ✅ {len(batch)} issues movidas com sucesso")


def fechar_sprint(sprint_id):
    """Fecha (completa) uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    body = {
        "state": "closed"
    }
    response = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    response.raise_for_status()
    print(f"  ✅ Sprint {sprint_id} fechada com sucesso")


def ativar_sprint(sprint_id, data_inicio, data_fim):
    """Ativa uma sprint (muda estado para 'active')."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    body = {
        "state": "active",
        "startDate": data_inicio,
        "endDate": data_fim
    }
    response = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    response.raise_for_status()
    print(f"  ✅ Sprint {sprint_id} ativada com sucesso")


def main():
    print("=" * 50)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL - RAJ")
    print("=" * 50)

    agora = datetime.now()
    print(f"\n📅 Data atual: {agora.strftime('%d/%m/%Y %H:%M')}")

    # 1. Buscar todas as sprints para determinar o próximo número
    print("\n📋 Buscando sprints existentes...")
    sprints_ativas = get_sprints(BOARD_ID, "active")
    sprints_futuras = get_sprints(BOARD_ID, "future")
    sprints_fechadas = get_sprints(BOARD_ID, "closed")

    todas_sprints = sprints_ativas + sprints_futuras + sprints_fechadas
    print(f"  Total de sprints encontradas: {len(todas_sprints)}")

    # 2. Determinar próximo número sequencial
    maior_numero = extrair_maior_numero_sprint(todas_sprints)
    proximo_numero = maior_numero + 1
    mes_atual = agora.strftime("%m")
    ano_atual = agora.strftime("%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    print(f"\n🆕 Nova sprint: {nome_nova_sprint}")

    # 3. Calcular datas
    data_inicio = agora.strftime("%Y-%m-%d")
    data_fim = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%d")
    print(f"  Início: {data_inicio} | Fim: {data_fim}")

    # 4. Processar sprints ativas vencidas
    print("\n🔍 Verificando sprints ativas vencidas...")
    issues_para_mover = []

    for sprint in sprints_ativas:
        end_date_str = sprint.get("endDate", "")
        if end_date_str:
            # Parse da data (formato ISO)
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).replace(tzinfo=None)

            if end_date < agora:
                print(f"\n  ⚠️  Sprint vencida: {sprint['name']} (ID: {sprint['id']})")
                print(f"     Venceu em: {end_date.strftime('%d/%m/%Y')}")

                # Buscar issues pendentes
                pendentes = get_issues_nao_concluidas(sprint["id"])
                print(f"     Issues pendentes: {len(pendentes)}")
                issues_para_mover.extend(pendentes)

                # Fechar a sprint vencida
                print(f"     Fechando sprint...")
                fechar_sprint(sprint["id"])
            else:
                print(f"  ✅ Sprint ativa ainda vigente: {sprint['name']} (vence em {end_date.strftime('%d/%m/%Y')})")

    # 5. Criar a nova sprint
    print(f"\n🏗️  Criando sprint: {nome_nova_sprint}...")
    nova_sprint = criar_sprint(nome_nova_sprint, data_inicio, data_fim, BOARD_ID)
    nova_sprint_id = nova_sprint["id"]
    print(f"  ✅ Sprint criada com ID: {nova_sprint_id}")

    # 6. Mover issues pendentes para a nova sprint
    if issues_para_mover:
        print(f"\n📦 Movendo {len(issues_para_mover)} issues para {nome_nova_sprint}...")
        mover_issues_para_sprint(nova_sprint_id, issues_para_mover)
    else:
        print("\n📦 Nenhuma issue pendente para mover.")

    # 7. Ativar a nova sprint
    print(f"\n▶️  Ativando sprint {nome_nova_sprint}...")
    ativar_sprint(nova_sprint_id, data_inicio, data_fim)

    # Resumo final
    print("\n" + "=" * 50)
    print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 50)
    print(f"  Sprint criada: {nome_nova_sprint}")
    print(f"  Issues movidas: {len(issues_para_mover)}")
    print(f"  Período: {data_inicio} → {data_fim}")
    print("=" * 50)


if __name__ == "__main__":
    main()
