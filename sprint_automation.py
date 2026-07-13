"""
Automação de Sprint Semanal - Jira Cloud
Projeto: RAJ | Board: configurável via env

Fluxo:
1. Busca sprint ativa no board
2. Se vencida: cria nova, move issues pendentes, fecha antiga, ativa nova
3. Se nenhuma ativa: cria e ativa nova sprint do zero
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# ============ CONFIGURAÇÃO ============

JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "").strip()
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "").strip()
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "").strip()
BOARD_ID = os.environ.get("BOARD_ID", "").strip()
DURACAO_DIAS = int(os.environ.get("DURACAO_SPRINT_DIAS", "7"))

# Validação
if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
    print("❌ ERRO: Variáveis de ambiente obrigatórias não configuradas!")
    print(f"   JIRA_DOMAIN: {'✅' if JIRA_DOMAIN else '❌ FALTANDO'}")
    print(f"   JIRA_EMAIL: {'✅' if JIRA_EMAIL else '❌ FALTANDO'}")
    print(f"   JIRA_API_TOKEN: {'✅' if JIRA_API_TOKEN else '❌ FALTANDO'}")
    print(f"   BOARD_ID: {'✅' if BOARD_ID else '❌ FALTANDO'}")
    sys.exit(1)

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

# Timezone São Paulo (UTC-3)
SP_TZ = timezone(timedelta(hours=-3))
AGORA = datetime.now(SP_TZ)
HOJE = AGORA.date()

# ============ FUNÇÕES ============

def api_get(endpoint):
    """GET request à API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    return resp

def api_post(endpoint, data):
    """POST request à API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=data)
    return resp

def api_put(endpoint, data):
    """PUT request à API do Jira."""
    url = f"{BASE_URL}{endpoint}"
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=data)
    return resp

def buscar_sprints(board_id, state):
    """Busca sprints do board por estado."""
    resp = api_get(f"/board/{board_id}/sprint?state={state}&maxResults=50")
    if resp.status_code == 200:
        return resp.json().get("values", [])
    return []

def buscar_maior_numero_sprint():
    """Encontra o maior número sequencial entre todas as sprints."""
    maior = 0
    for state in ["active", "future", "closed"]:
        sprints = buscar_sprints(BOARD_ID, state)
        for s in sprints:
            nome = s.get("name", "")
            # Extrai número do padrão "Sprint XX - ..."
            import re
            match = re.search(r"Sprint\s+(\d+)", nome)
            if match:
                num = int(match.group(1))
                if num > maior:
                    maior = num
    return maior

def buscar_issues_pendentes(sprint_id):
    """Busca issues não concluídas de uma sprint."""
    resp = api_get(f"/sprint/{sprint_id}/issue?maxResults=200&fields=status")
    if resp.status_code == 200:
        issues = resp.json().get("issues", [])
        pendentes = []
        for issue in issues:
            status_cat = issue["fields"]["status"]["statusCategory"]["key"]
            if status_cat != "done":
                pendentes.append(issue["key"])
        return pendentes
    return []

def criar_sprint(nome, inicio, fim):
    """Cria uma nova sprint (estado future)."""
    data = {
        "name": nome,
        "startDate": inicio,
        "endDate": fim,
        "originBoardId": int(BOARD_ID),
        "goal": "Sprint criada automaticamente"
    }
    resp = api_post("/sprint", data)
    if resp.status_code == 201:
        sprint = resp.json()
        print(f"   ✅ Sprint criada! ID: {sprint['id']}")
        return sprint
    else:
        print(f"   ❌ Erro ao criar sprint: {resp.status_code}")
        print(f"      Resposta: {resp.text}")
        sys.exit(1)

def mover_issues(sprint_id, issue_keys):
    """Move issues para uma sprint."""
    if not issue_keys:
        return True
    data = {"issues": issue_keys}
    resp = api_post(f"/sprint/{sprint_id}/issue", data)
    if resp.status_code in [200, 204]:
        print(f"   ✅ {len(issue_keys)} issues movidas com sucesso")
        return True
    else:
        print(f"   ⚠️ Erro ao mover issues: {resp.status_code}")
        print(f"      Resposta: {resp.text}")
        return False

def fechar_sprint(sprint_id, sprint_name):
    """Fecha uma sprint. Inclui name obrigatoriamente."""
    data = {
        "name": sprint_name,
        "state": "closed",
        "completeDate": AGORA.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
    }
    resp = api_put(f"/sprint/{sprint_id}", data)
    if resp.status_code == 200:
        print(f"   ✅ Sprint fechada com sucesso")
        return True
    else:
        print(f"   ❌ Erro ao fechar: {resp.status_code}")
        print(f"      Resposta: {resp.text}")
        # Tentativa alternativa sem completeDate
        data2 = {"name": sprint_name, "state": "closed"}
        resp2 = api_put(f"/sprint/{sprint_id}", data2)
        if resp2.status_code == 200:
            print(f"   ✅ Sprint fechada (segunda tentativa)")
            return True
        else:
            print(f"   ❌ Falha definitiva ao fechar: {resp2.status_code}")
            print(f"      Resposta: {resp2.text}")
            return False

def ativar_sprint(sprint_id, sprint_name, inicio, fim):
    """Ativa uma sprint. Inclui name obrigatoriamente."""
    data = {
        "name": sprint_name,
        "state": "active",
        "startDate": inicio,
        "endDate": fim
    }
    resp = api_put(f"/sprint/{sprint_id}", data)
    if resp.status_code == 200:
        print(f"   ✅ Sprint ativada com sucesso")
        return True
    else:
        print(f"   ❌ Erro ao ativar: {resp.status_code}")
        print(f"      Resposta: {resp.text}")
        return False

# ============ EXECUÇÃO PRINCIPAL ============

def main():
    print("=" * 55)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL")
    print("=" * 55)
    print()
    print(f"📅 Data atual (São Paulo): {AGORA.strftime('%d/%m/%Y %H:%M')}")
    print(f"📋 Board ID: {BOARD_ID}")
    print(f"⏱️ Duração da sprint: {DURACAO_DIAS} dias")
    print()

    # Datas da nova sprint
    data_inicio = HOJE.strftime("%Y-%m-%d")
    data_fim = (HOJE + timedelta(days=DURACAO_DIAS)).strftime("%Y-%m-%d")

    # Buscar sprint ativa
    print("🔍 Buscando sprints ativas...")
    sprints_ativas = buscar_sprints(BOARD_ID, "active")

    if sprints_ativas:
        sprint_atual = sprints_ativas[0]
        sprint_id = sprint_atual["id"]
        sprint_nome = sprint_atual["name"]
        end_date_str = sprint_atual.get("endDate", "")

        print(f"   📌 Sprint ativa: {sprint_nome} (ID: {sprint_id})")

        # Verificar se venceu
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).date()
            print(f"   📆 Vence em: {end_date.strftime('%d/%m/%Y')}")

            if end_date <= HOJE:
                print(f"   ⚠️ Sprint VENCIDA! Processando...")
                print()

                # Buscar issues pendentes
                issues_pendentes = buscar_issues_pendentes(sprint_id)
                print(f"   📝 Issues pendentes: {len(issues_pendentes)}")

                # Calcular próximo número
                maior_num = buscar_maior_numero_sprint()
                proximo_num = maior_num + 1
                mes_ano = f"{HOJE.month:02d}/{HOJE.year}"
                novo_nome = f"Sprint {proximo_num} - {mes_ano}"

                print()
                print(f"📦 Criando: {novo_nome}")
                print(f"   Início: {data_inicio} | Fim: {data_fim}")

                # Criar nova sprint
                nova_sprint = criar_sprint(novo_nome, data_inicio, data_fim)
                nova_sprint_id = nova_sprint["id"]

                # Mover issues pendentes
                if issues_pendentes:
                    print()
                    print(f"🔄 Movendo {len(issues_pendentes)} issues para {novo_nome}...")
                    mover_issues(nova_sprint_id, issues_pendentes)

                # Fechar sprint antiga
                print()
                print(f"🔒 Fechando {sprint_nome}...")
                fechar_sprint(sprint_id, sprint_nome)

                # Ativar nova sprint
                print()
                print(f"▶️ Ativando {novo_nome}...")
                ativar_sprint(nova_sprint_id, novo_nome, data_inicio, data_fim)

            else:
                print(f"   ✅ Sprint ainda vigente. Nada a fazer.")
                print(f"   Próxima execução relevante após {end_date.strftime('%d/%m/%Y')}")
        else:
            print("   ⚠️ Sprint sem data de fim definida. Pulando.")
    else:
        print("   ℹ️ Nenhuma sprint ativa encontrada.")
        print("   Criando nova sprint do zero...")
        print()

        # Calcular próximo número
        maior_num = buscar_maior_numero_sprint()
        proximo_num = maior_num + 1
        mes_ano = f"{HOJE.month:02d}/{HOJE.year}"
        novo_nome = f"Sprint {proximo_num} - {mes_ano}"

        print(f"📦 Criando: {novo_nome}")
        print(f"   Início: {data_inicio} | Fim: {data_fim}")

        # Criar
        nova_sprint = criar_sprint(novo_nome, data_inicio, data_fim)
        nova_sprint_id = nova_sprint["id"]

        # Ativar
        print()
        print(f"▶️ Ativando {novo_nome}...")
        ativar_sprint(nova_sprint_id, novo_nome, data_inicio, data_fim)

    print()
    print("=" * 55)
    print("✅ AUTOMAÇÃO CONCLUÍDA")
    print("=" * 55)

if __name__ == "__main__":
    main()
