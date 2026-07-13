"""
Automação de Sprints Semanais - Jira Cloud
Board: RAJ (ID configurável via env)
Ações: Cria nova sprint, move issues pendentes, fecha sprint vencida, ativa a nova.
"""

import os
import sys
import requests
from datetime import datetime, timedelta
import pytz

# ========== CONFIGURAÇÕES ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
BOARD_ID = os.environ.get("BOARD_ID")

# Validar variáveis de ambiente
if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
    print("❌ ERRO: Variáveis de ambiente não configuradas!")
    print(f"   JIRA_DOMAIN: {'✅' if JIRA_DOMAIN else '❌ FALTANDO'}")
    print(f"   JIRA_EMAIL: {'✅' if JIRA_EMAIL else '❌ FALTANDO'}")
    print(f"   JIRA_API_TOKEN: {'✅' if JIRA_API_TOKEN else '❌ FALTANDO'}")
    print(f"   BOARD_ID: {'✅' if BOARD_ID else '❌ FALTANDO'}")
    sys.exit(1)

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

# Timezone Brasil
TZ_BRASIL = pytz.timezone("America/Sao_Paulo")
AGORA = datetime.now(TZ_BRASIL)
HOJE_DATE = AGORA.date()

DURACAO_SPRINT_DIAS = 7


def api_get(endpoint):
    """GET request para a API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, auth=AUTH, headers=HEADERS)
    return response


def api_post(endpoint, data):
    """POST request para a API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    response = requests.post(url, auth=AUTH, headers=HEADERS, json=data)
    return response


def api_put(endpoint, data):
    """PUT request para a API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    response = requests.put(url, auth=AUTH, headers=HEADERS, json=data)
    return response


def get_sprints(board_id, state):
    """Busca sprints do board por estado."""
    sprints = []
    start_at = 0
    while True:
        resp = api_get(f"/board/{board_id}/sprint?state={state}&startAt={start_at}&maxResults=50")
        if resp.status_code != 200:
            print(f"⚠️ Erro ao buscar sprints ({state}): {resp.status_code}")
            break
        data = resp.json()
        sprints.extend(data.get("values", []))
        if data.get("isLast", True):
            break
        start_at += 50
    return sprints


def get_issues_pendentes(sprint_id):
    """Busca issues NÃO concluídas de uma sprint."""
    issues = []
    start_at = 0
    while True:
        resp = api_get(f"/sprint/{sprint_id}/issue?startAt={start_at}&maxResults=100&fields=status")
        if resp.status_code != 200:
            print(f"⚠️ Erro ao buscar issues da sprint {sprint_id}: {resp.status_code}")
            break
        data = resp.json()
        for issue in data.get("issues", []):
            status_category = issue["fields"]["status"]["statusCategory"]["key"]
            if status_category != "done":
                issues.append(issue["key"])
        if start_at + 100 >= data.get("total", 0):
            break
        start_at += 100
    return issues


def extrair_numero_sprint(nome):
    """Extrai o número sequencial do nome da sprint (ex: 'Sprint 48 - 07/2026' → 48)."""
    import re
    match = re.search(r"Sprint\s+(\d+)", nome)
    if match:
        return int(match.group(1))
    return 0


def main():
    print("=" * 60)
    print(f"🚀 Automação de Sprint Semanal - {AGORA.strftime('%d/%m/%Y %H:%M')}")
    print(f"   Board ID: {BOARD_ID} | Domain: {JIRA_DOMAIN}")
    print("=" * 60)

    # 1. Buscar sprints ativas
    print("\n📋 Buscando sprints ativas...")
    sprints_ativas = get_sprints(BOARD_ID, "active")
    print(f"   Encontradas: {len(sprints_ativas)} sprint(s) ativa(s)")

    # 2. Buscar todas as sprints para determinar o próximo número
    sprints_futuras = get_sprints(BOARD_ID, "future")
    sprints_fechadas = get_sprints(BOARD_ID, "closed")

    todas_sprints = sprints_ativas + sprints_futuras + sprints_fechadas
    maior_numero = 0
    for s in todas_sprints:
        num = extrair_numero_sprint(s.get("name", ""))
        if num > maior_numero:
            maior_numero = num

    proximo_numero = maior_numero + 1
    mes_atual = AGORA.strftime("%m")
    ano_atual = AGORA.strftime("%Y")
    nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"

    print(f"\n🆕 Próxima sprint: {nome_nova_sprint}")

    # 3. Calcular datas da nova sprint
    data_inicio = AGORA.strftime("%Y-%m-%d")
    data_fim = (AGORA + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%d")

    # 4. Criar a nova sprint (estado FUTURE primeiro)
    print(f"\n📌 Criando sprint '{nome_nova_sprint}'...")
    create_payload = {
        "name": nome_nova_sprint,
        "originBoardId": int(BOARD_ID),
        "goal": "Sprint criada automaticamente"
    }

    resp_create = api_post("/sprint", create_payload)
    if resp_create.status_code not in [200, 201]:
        print(f"❌ Erro ao criar sprint: {resp_create.status_code}")
        print(f"   Response: {resp_create.text}")
        sys.exit(1)

    nova_sprint = resp_create.json()
    nova_sprint_id = nova_sprint["id"]
    print(f"   ✅ Sprint criada! ID: {nova_sprint_id}")

    # 5. Processar sprints ativas vencidas
    sprint_fechada = False
    for sprint_ativa in sprints_ativas:
        end_date_str = sprint_ativa.get("endDate", "")
        if not end_date_str:
            print(f"   ⚠️ Sprint '{sprint_ativa['name']}' sem data de fim, pulando...")
            continue

        # Parsear a data de fim (formato ISO: 2026-07-13T...)
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).astimezone(TZ_BRASIL).date()

        print(f"\n🔍 Sprint ativa: {sprint_ativa['name']} (ID: {sprint_ativa['id']})")
        print(f"   Data fim: {end_date.strftime('%d/%m/%Y')} | Hoje: {HOJE_DATE.strftime('%d/%m/%Y')}")

        # Se a sprint venceu (data fim <= hoje)
        if end_date <= HOJE_DATE:
            print(f"   ⚠️ Sprint VENCIDA! Processando...")

            # 5a. Mover issues pendentes para a nova sprint
            issues_pendentes = get_issues_pendentes(sprint_ativa["id"])
            print(f"   📦 Issues pendentes: {len(issues_pendentes)}")

            if issues_pendentes:
                print(f"   🔄 Movendo issues para '{nome_nova_sprint}'...")
                move_payload = {"issues": issues_pendentes}
                resp_move = api_post(f"/sprint/{nova_sprint_id}/issue", move_payload)

                if resp_move.status_code in [200, 204]:
                    print(f"   ✅ {len(issues_pendentes)} issues movidas com sucesso!")
                else:
                    print(f"   ❌ Erro ao mover issues: {resp_move.status_code}")
                    print(f"      Response: {resp_move.text}")

            # 5b. Fechar a sprint vencida
            # No Jira Cloud, basta setar state: "closed" — as issues já foram movidas
            print(f"   🔒 Fechando sprint '{sprint_ativa['name']}'...")
            close_payload = {
                "state": "closed"
            }
            resp_close = api_put(f"/sprint/{sprint_ativa['id']}", close_payload)

            if resp_close.status_code == 200:
                print(f"   ✅ Sprint fechada com sucesso!")
                sprint_fechada = True
            else:
                print(f"   ❌ Erro ao fechar sprint: {resp_close.status_code}")
                print(f"      Response: {resp_close.text}")
                # Tentar com completeDate explícito
                print(f"   🔄 Tentando com completeDate...")
                close_payload_v2 = {
                    "state": "closed",
                    "completeDate": AGORA.strftime("%Y-%m-%dT%H:%M:%S.000%z")
                }
                resp_close_v2 = api_put(f"/sprint/{sprint_ativa['id']}", close_payload_v2)
                if resp_close_v2.status_code == 200:
                    print(f"   ✅ Sprint fechada com sucesso (tentativa 2)!")
                    sprint_fechada = True
                else:
                    print(f"   ❌ Falha definitiva ao fechar: {resp_close_v2.status_code}")
                    print(f"      Response: {resp_close_v2.text}")
        else:
            dias_restantes = (end_date - HOJE_DATE).days
            print(f"   ✅ Sprint ainda vigente ({dias_restantes} dia(s) restante(s))")

    # 6. Ativar a nova sprint (setar state: "active" com datas)
    print(f"\n🟢 Ativando sprint '{nome_nova_sprint}'...")
    activate_payload = {
        "state": "active",
        "startDate": f"{data_inicio}T08:00:00.000-0300",
        "endDate": f"{data_fim}T18:00:00.000-0300"
    }
    resp_activate = api_put(f"/sprint/{nova_sprint_id}", activate_payload)

    if resp_activate.status_code == 200:
        print(f"   ✅ Sprint ativada com sucesso!")
        print(f"   📅 Período: {data_inicio} até {data_fim}")
    else:
        print(f"   ❌ Erro ao ativar sprint: {resp_activate.status_code}")
        print(f"      Response: {resp_activate.text}")

    # 7. Resumo final
    print("\n" + "=" * 60)
    print("📊 RESUMO DA EXECUÇÃO:")
    print(f"   • Nova sprint: {nome_nova_sprint} (ID: {nova_sprint_id})")
    print(f"   • Período: {data_inicio} → {data_fim}")
    print(f"   • Sprint anterior fechada: {'✅ Sim' if sprint_fechada else '⚠️ Não (verifique logs)'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
