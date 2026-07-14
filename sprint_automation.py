import os
import sys
import re
import json
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("ERRO: módulo 'requests' não encontrado. Instale com: pip install requests")
    sys.exit(1)

# ========== CONFIGURAÇÕES ==========
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

DURACAO_SPRINT_DIAS = 7
FUSO_HORARIO = timezone(timedelta(hours=-3))  # America/Sao_Paulo

# ========== VALIDAÇÃO ==========
if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
    print("❌ ERRO: Variáveis de ambiente obrigatórias não configuradas!")
    print("   Necessárias: JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID")
    sys.exit(1)

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


# ========== FUNÇÕES AUXILIARES ==========

def get_todas_sprints(board_id):
    """Busca TODAS as sprints do board, paginando por todos os estados."""
    todas = []
    for state in ["active", "future", "closed"]:
        start_at = 0
        while True:
            url = f"{BASE_URL}/board/{board_id}/sprint?state={state}&startAt={start_at}&maxResults=50"
            resp = requests.get(url, auth=AUTH, headers=HEADERS)
            if resp.status_code != 200:
                print(f"   ⚠️ Erro ao buscar sprints ({state}): {resp.status_code}")
                break
            data = resp.json()
            valores = data.get("values", [])
            todas.extend(valores)
            if data.get("isLast", True):
                break
            start_at += len(valores)
    return todas


def extrair_maior_numero(sprints):
    """Extrai o maior número sequencial das sprints existentes."""
    maior = 0
    for sprint in sprints:
        match = re.search(r"Sprint\s+(\d+)", sprint.get("name", ""))
        if match:
            num = int(match.group(1))
            if num > maior:
                maior = num
    return maior


def get_sprints_ativas(board_id):
    """Busca apenas sprints ativas."""
    url = f"{BASE_URL}/board/{board_id}/sprint?state=active"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json().get("values", [])
    return []


def get_issues_sprint(sprint_id):
    """Busca todas as issues de uma sprint com paginação."""
    issues = []
    start_at = 0
    while True:
        url = f"{BASE_URL}/sprint/{sprint_id}/issue?startAt={start_at}&maxResults=100&fields=status,summary"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            break
        data = resp.json()
        issues.extend(data.get("issues", []))
        if start_at + len(data.get("issues", [])) >= data.get("total", 0):
            break
        start_at += len(data.get("issues", []))
    return issues


def criar_sprint(board_id, nome):
    """Cria uma nova sprint no estado future."""
    url = f"{BASE_URL}/sprint"
    body = {"name": nome, "originBoardId": int(board_id)}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 201:
        return resp.json()
    print(f"   ❌ Erro ao criar sprint: {resp.status_code}")
    print(f"   Resposta: {resp.text}")
    return None


def mover_issues_para_sprint(sprint_id, issue_keys):
    """Move issues para uma sprint."""
    if not issue_keys:
        return True
    url = f"{BASE_URL}/sprint/{sprint_id}/issue"
    body = {"issues": issue_keys}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code in [200, 204]:
        return True
    print(f"   ❌ Erro ao mover issues: {resp.status_code}")
    print(f"   Resposta: {resp.text}")
    return False


def fechar_sprint(sprint_id, nome):
    """Fecha uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    body = {"name": nome, "state": "closed"}
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 200:
        return True
    print(f"   ❌ Erro ao fechar sprint: {resp.status_code}")
    print(f"   Resposta: {resp.text}")
    # Tentativa alternativa com completeDate
    agora = datetime.now(FUSO_HORARIO).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
    body2 = {"name": nome, "state": "closed", "completeDate": agora}
    resp2 = requests.put(url, auth=AUTH, headers=HEADERS, json=body2)
    if resp2.status_code == 200:
        return True
    print(f"   ❌ Tentativa 2 também falhou: {resp2.status_code}")
    print(f"   Resposta: {resp2.text}")
    return False


def ativar_sprint(sprint_id, nome, data_inicio, data_fim):
    """Ativa uma sprint (muda de future para active)."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    body = {
        "name": nome,
        "state": "active",
        "startDate": data_inicio,
        "endDate": data_fim
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=body)
    if resp.status_code == 200:
        return True
    print(f"   ❌ Erro ao ativar sprint: {resp.status_code}")
    print(f"   Resposta: {resp.text}")
    return False


def enviar_notificacao_teams(sprint_fechada_nome, sprint_nova_nome, issues_concluidas, issues_movidas):
    """Envia resumo semanal para o Microsoft Teams via webhook."""
    if not TEAMS_WEBHOOK_URL:
        print("\n📢 Notificação Teams: TEAMS_WEBHOOK_URL não configurada, pulando...")
        return

    print("\n📢 Enviando notificação para o Teams...")

    # Montar lista de tarefas finalizadas
    if issues_concluidas:
        lista_concluidas = "\n".join([f"• {i['key']} — {i['summary']}" for i in issues_concluidas])
    else:
        lista_concluidas = "• Nenhuma tarefa finalizada nesta sprint"

    # Montar lista de tarefas transferidas
    if issues_movidas:
        lista_movidas = "\n".join([f"• {i['key']} — {i['summary']}" for i in issues_movidas])
    else:
        lista_movidas = "• Nenhuma tarefa transferida"

    # Cartão adaptativo para Teams
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": f"🏁 Sprint concluída: {sprint_fechada_nome}",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"✅ **Tarefas finalizadas ({len(issues_concluidas)}):**",
                            "wrap": True,
                            "weight": "Bolder",
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_concluidas,
                            "wrap": True,
                            "spacing": "Small"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"🔄 **Transferidas → {sprint_nova_nome} ({len(issues_movidas)}):**",
                            "wrap": True,
                            "weight": "Bolder",
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_movidas,
                            "wrap": True,
                            "spacing": "Small"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"📅 {datetime.now(FUSO_HORARIO).strftime('%d/%m/%Y às %H:%M')}",
                            "wrap": True,
                            "spacing": "Large",
                            "isSubtle": True
                        }
                    ]
                }
            }
        ]
    }

    try:
        resp = requests.post(TEAMS_WEBHOOK_URL, json=card, headers={"Content-Type": "application/json"})
        if resp.status_code in [200, 202]:
            print("   ✅ Notificação enviada com sucesso!")
        else:
            print(f"   ⚠️ Webhook retornou: {resp.status_code}")
            print(f"   Resposta: {resp.text}")
    except Exception as e:
        print(f"   ⚠️ Erro ao enviar notificação: {e}")
        # Não falha o script por causa da notificação


# ========== LÓGICA PRINCIPAL ==========

def main():
    print("=" * 50)
    print("🚀 AUTOMAÇÃO DE SPRINT SEMANAL")
    print(f"   Board ID: {BOARD_ID}")
    print(f"   Domínio: {JIRA_DOMAIN}")
    agora = datetime.now(FUSO_HORARIO)
    print(f"   Data/Hora: {agora.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 50)

    # 1. Buscar todas as sprints para encontrar o maior número
    print("\n📋 Buscando todas as sprints do board...")
    todas_sprints = get_todas_sprints(BOARD_ID)
    print(f"   Total encontradas: {len(todas_sprints)}")

    maior_numero = extrair_maior_numero(todas_sprints)
    print(f"   Maior número sequencial: {maior_numero}")

    # 2. Verificar sprints ativas
    print("\n🔍 Verificando sprints ativas...")
    sprints_ativas = get_sprints_ativas(BOARD_ID)

    # Variáveis para notificação
    sprint_fechada_nome = None
    sprint_nova_nome = None
    issues_concluidas_info = []
    issues_movidas_info = []

    if sprints_ativas:
        sprint_ativa = sprints_ativas[0]
        print(f"   Sprint ativa: {sprint_ativa['name']} (ID: {sprint_ativa['id']})")

        # Verificar se está vencida
        end_date_str = sprint_ativa.get("endDate", "")
        if not end_date_str:
            print("   ⚠️ Sprint ativa sem data de fim. Nada a fazer.")
            print("\n✅ AUTOMAÇÃO CONCLUÍDA — nenhuma ação necessária")
            return

        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).astimezone(FUSO_HORARIO).date()
        hoje_date = agora.date()

        print(f"   Data fim: {end_date.strftime('%d/%m/%Y')}")
        print(f"   Hoje: {hoje_date.strftime('%d/%m/%Y')}")

        if end_date <= hoje_date:
            print(f"\n⚠️ Sprint vencida! Processando...")

            # 3. Buscar issues da sprint
            print("\n📦 Buscando issues da sprint...")
            issues = get_issues_sprint(sprint_ativa["id"])
            print(f"   Total de issues: {len(issues)}")

            # Separar concluídas e pendentes
            issues_pendentes = []
            issues_concluidas = []
            for issue in issues:
                status_category = issue["fields"]["status"]["statusCategory"]["key"]
                issue_info = {
                    "key": issue["key"],
                    "summary": issue["fields"].get("summary", "Sem título")
                }
                if status_category == "done":
                    issues_concluidas.append(issue_info)
                else:
                    issues_pendentes.append(issue_info)

            print(f"   ✅ Concluídas: {len(issues_concluidas)}")
            print(f"   🔄 Pendentes (serão movidas): {len(issues_pendentes)}")

            # Guardar para notificação
            issues_concluidas_info = issues_concluidas
            issues_movidas_info = issues_pendentes
            sprint_fechada_nome = sprint_ativa["name"]

            # 4. Calcular próxima sprint
            proximo_numero = maior_numero + 1
            mes_atual = agora.strftime("%m")
            ano_atual = agora.strftime("%Y")
            nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"
            sprint_nova_nome = nome_nova_sprint

            print(f"\n🆕 Criando: {nome_nova_sprint}")
            nova_sprint = criar_sprint(BOARD_ID, nome_nova_sprint)
            if not nova_sprint:
                print("❌ FALHA: Não foi possível criar a sprint")
                sys.exit(1)
            print(f"   ✅ Sprint criada! ID: {nova_sprint['id']}")

            # 5. Mover issues pendentes
            if issues_pendentes:
                print(f"\n📦 Movendo {len(issues_pendentes)} issues para {nome_nova_sprint}...")
                issue_keys = [i["key"] for i in issues_pendentes]
                if mover_issues_para_sprint(nova_sprint["id"], issue_keys):
                    print("   ✅ Issues movidas com sucesso!")
                else:
                    print("   ⚠️ Problema ao mover issues")

            # 6. Fechar sprint antiga
            print(f"\n🔒 Fechando {sprint_ativa['name']}...")
            if fechar_sprint(sprint_ativa["id"], sprint_ativa["name"]):
                print("   ✅ Sprint fechada com sucesso!")
            else:
                print("   ⚠️ Não foi possível fechar a sprint")

            # 7. Ativar nova sprint
            data_inicio = agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
            data_fim_nova = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

            print(f"\n▶️ Ativando {nome_nova_sprint}...")
            if ativar_sprint(nova_sprint["id"], nome_nova_sprint, data_inicio, data_fim_nova):
                print("   ✅ Sprint ativada com sucesso!")
            else:
                print("   ⚠️ Não foi possível ativar a sprint")

            print(f"\n{'=' * 50}")
            print("✅ AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
            print(f"   Sprint fechada: {sprint_ativa['name']}")
            print(f"   Sprint nova: {nome_nova_sprint}")
            print(f"   Issues movidas: {len(issues_pendentes)}")
            print(f"{'=' * 50}")

            # 8. Enviar notificação Teams (último passo — não afeta o resto)
            enviar_notificacao_teams(sprint_fechada_nome, sprint_nova_nome, issues_concluidas_info, issues_movidas_info)

        else:
            dias_restantes = (end_date - hoje_date).days
            print(f"\n✅ Sprint ainda vigente. Vence em {dias_restantes} dia(s).")
            print("   Nenhuma ação necessária.")

    else:
        # Sem sprint ativa — criar e ativar uma nova
        print("   Nenhuma sprint ativa encontrada.")

        proximo_numero = maior_numero + 1
        mes_atual = agora.strftime("%m")
        ano_atual = agora.strftime("%Y")
        nome_nova_sprint = f"Sprint {proximo_numero} - {mes_atual}/{ano_atual}"
        sprint_nova_nome = nome_nova_sprint

        print(f"\n🆕 Criando: {nome_nova_sprint}")
        nova_sprint = criar_sprint(BOARD_ID, nome_nova_sprint)
        if not nova_sprint:
            print("❌ FALHA: Não foi possível criar a sprint")
            sys.exit(1)
        print(f"   ✅ Sprint criada! ID: {nova_sprint['id']}")

        # Ativar
        data_inicio = agora.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
        data_fim_nova = (agora + timedelta(days=DURACAO_SPRINT_DIAS)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

        print(f"\n▶️ Ativando {nome_nova_sprint}...")
        if ativar_sprint(nova_sprint["id"], nome_nova_sprint, data_inicio, data_fim_nova):
            print("   ✅ Sprint ativada com sucesso!")
        else:
            print("   ⚠️ Não foi possível ativar a sprint")

        print(f"\n{'=' * 50}")
        print("✅ AUTOMAÇÃO CONCLUÍDA!")
        print(f"   Sprint criada e ativada: {nome_nova_sprint}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
