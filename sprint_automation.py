import requests
import os
from datetime import datetime, timedelta
import re

# ========== CONFIGURAÇÕES ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
BOARD_ID = os.environ.get("BOARD_ID")

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

DURACAO_SPRINT_DIAS = 7


def get_sprints(state):
    """Busca sprints do board por estado"""
    url = f"{BASE_URL}/board/{BOARD_ID}/sprint?state={state}&maxResults=50"
    response = requests.get(url, auth=AUTH, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("values", [])
    print(f"⚠️ Erro ao buscar sprints ({state}): {response.status_code}")
    return []


def get_issues_pendentes(sprint_id):
    """Busca issues NÃO concluídas de uma sprint"""
    url = f"{BASE_URL}/sprint/{sprint_id}/issue?maxResults=200&fields=status"
    response = requests.get(url, auth=AUTH, headers=HEADERS)
    if response.status_code == 200:
        issues = response.json().get("issues", [])
        pendentes = [
            issue["key"] for issue in issues
            if issue["fields"]["status"]["statusCategory"]["key"] != "done"
        ]
        return pendentes
    return []


def extrair_maior_numero(sprints):
    """Extrai o maior número sequencial das sprints"""
    maior = 0
    for sprint in sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior:
                maior = num
    return maior


def main():
    print("=" * 50)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL")
    print("=" * 50)
    print(f"📅 Data atual: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"🎯 Board ID: {BOARD_ID}")
    print()

    # 1. Buscar sprints
    sprints_ativas = get_sprints("active")
    sprints_futuras = get_sprints("future")
    sprints_fechadas = get_sprints("closed")

    todas_sprints = sprints_ativas + sprints_futuras + sprints_fechadas

    # 2. Calcular próximo número
    maior_numero = extrair_maior_numero(todas_sprints)
    proximo_numero = maior_numero + 1

    # 3. Calcular nome e datas
    hoje = datetime.now()
    mes_atual = hoje.strftime("%m")
    ano_atual = hoje.strftime("%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    data_inicio = hoje.strftime("%Y-%m-%d")
    data_fim = (hoje + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%d")

    print(f"📋 Próxima sprint: {nome_nova_sprint}")
    print(f"   Início: {data_inicio} | Fim: {data_fim}")
    print()

    # 4. Criar nova sprint (em estado FUTURO, sem ativar ainda)
    print("➡️ Criando nova sprint...")
    create_body = {
        "name": nome_nova_sprint,
        "originBoardId": int(BOARD_ID),
        "goal": "Sprint criada automaticamente"
    }

    response = requests.post(f"{BASE_URL}/sprint", auth=AUTH, headers=HEADERS, json=create_body)

    if response.status_code != 201:
        print(f"❌ Erro ao criar sprint: {response.status_code} - {response.text}")
        return

    nova_sprint = response.json()
    nova_sprint_id = nova_sprint["id"]
    print(f"✅ Sprint criada: {nome_nova_sprint} (ID: {nova_sprint_id})")
    print()

    # 5. Processar sprints ativas vencidas
    sprint_fechada = False
    for sprint in sprints_ativas:
        end_date_str = sprint.get("endDate", "")
        if not end_date_str:
            continue

        # Parse da data de fim (pega só a parte da data)
        end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d")
        hoje_date = datetime(hoje.year, hoje.month, hoje.day)

        print(f"🔍 Verificando: {sprint['name']}")
        print(f"   Data fim: {end_date.strftime('%d/%m/%Y')} | Hoje: {hoje_date.strftime('%d/%m/%Y')}")

        # CORREÇÃO: usar <= (menor ou igual) para incluir sprints que vencem HOJE
        if end_date <= hoje_date:
            print(f"⚠️ Sprint vencida: {sprint['name']} (ID: {sprint['id']})")

            # 6. Buscar issues pendentes
            issues_pendentes = get_issues_pendentes(sprint["id"])
            print(f"   Issues pendentes: {len(issues_pendentes)}")

            # 7. Mover issues pendentes para nova sprint
            if issues_pendentes:
                print(f"   Movendo issues para {nome_nova_sprint}...")
                move_body = {"issues": issues_pendentes}
                move_response = requests.post(
                    f"{BASE_URL}/sprint/{nova_sprint_id}/issue",
                    auth=AUTH, headers=HEADERS, json=move_body
                )
                if move_response.status_code == 204:
                    print(f"   ✅ {len(issues_pendentes)} issues movidas com sucesso")
                else:
                    print(f"   ⚠️ Resposta ao mover: {move_response.status_code} - {move_response.text}")

            # 8. FECHAR a sprint vencida (ANTES de ativar a nova)
            print(f"   Fechando sprint {sprint['name']}...")
            close_body = {
                "state": "closed",
                "completeDate": hoje.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "moveUnfixedIssuesTo": nova_sprint_id
            }
            close_response = requests.put(
                f"{BASE_URL}/sprint/{sprint['id']}",
                auth=AUTH, headers=HEADERS, json=close_body
            )

            if close_response.status_code == 200:
                print(f"   ✅ Sprint {sprint['name']} fechada com sucesso!")
                sprint_fechada = True
            else:
                print(f"   ❌ Erro ao fechar: {close_response.status_code} - {close_response.text}")
        else:
            print(f"   ℹ️ Sprint ainda vigente, não será fechada")

    print()

    # 9. ATIVAR a nova sprint (só depois de fechar a anterior)
    print(f"➡️ Ativando {nome_nova_sprint}...")
    activate_body = {
        "state": "active",
        "startDate": f"{data_inicio}T08:00:00.000Z",
        "endDate": f"{data_fim}T08:00:00.000Z"
    }
    activate_response = requests.put(
        f"{BASE_URL}/sprint/{nova_sprint_id}",
        auth=AUTH, headers=HEADERS, json=activate_body
    )

    if activate_response.status_code == 200:
        print(f"✅ {nome_nova_sprint} ativada com sucesso!")
    else:
        print(f"❌ Erro ao ativar: {activate_response.status_code} - {activate_response.text}")

    # 10. Resumo final
    print()
    print("=" * 50)
    print("📊 RESUMO")
    print("=" * 50)
    print(f"✅ Sprint criada e ativada: {nome_nova_sprint}")
    if sprint_fechada:
        print(f"✅ Sprint anterior fechada")
    print(f"🎯 Próxima execução: próxima segunda-feira")


if __name__ == "__main__":
    main()
