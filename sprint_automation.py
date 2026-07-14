import os
import sys
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# CONFIGURAÇÕES (via variáveis de ambiente / GitHub Secrets)
# ============================================================
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID = os.environ.get("BOARD_ID", "")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, BOARD_ID]):
    print("❌ Variáveis de ambiente obrigatórias não configuradas!")
    sys.exit(1)

BASE_URL = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# Fuso horário Brasil (UTC-3)
BR_TZ = timezone(timedelta(hours=-3))


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def get_todas_sprints():
    """Busca TODAS as sprints do board (paginando) para encontrar o maior número."""
    todas = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/board/{BOARD_ID}/sprint?startAt={start_at}&maxResults={max_results}"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro ao buscar sprints: {resp.status_code}")
            print(f"Resposta: {resp.text}")
            sys.exit(1)

        data = resp.json()
        sprints = data.get("values", [])
        todas.extend(sprints)

        if data.get("isLast", True):
            break
        start_at += max_results

    return todas


def get_sprint_ativa():
    """Retorna a sprint ativa do board, se existir."""
    url = f"{BASE_URL}/board/{BOARD_ID}/sprint?state=active"
    resp = requests.get(url, auth=AUTH, headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Erro ao buscar sprint ativa: {resp.status_code}")
        print(f"Resposta: {resp.text}")
        sys.exit(1)

    sprints = resp.json().get("values", [])
    if sprints:
        return sprints[0]
    return None


def get_issues_sprint(sprint_id):
    """Retorna todas as issues de uma sprint."""
    issues = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{BASE_URL}/sprint/{sprint_id}/issue?startAt={start_at}&maxResults={max_results}"
        resp = requests.get(url, auth=AUTH, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro ao buscar issues: {resp.status_code}")
            return issues

        data = resp.json()
        issues.extend(data.get("issues", []))

        if start_at + max_results >= data.get("total", 0):
            break
        start_at += max_results

    return issues


def extrair_maior_numero(sprints):
    """Extrai o maior número de sprint a partir dos nomes (ex: 'Sprint 48 - 07/2026' → 48)."""
    maior = 0
    for s in sprints:
        nome = s.get("name", "")
        # Tenta extrair número após "Sprint "
        if "Sprint" in nome or "sprint" in nome:
            partes = nome.split()
            for i, p in enumerate(partes):
                if p.lower() == "sprint" and i + 1 < len(partes):
                    try:
                        num = int(partes[i + 1].replace("-", "").replace(",", ""))
                        if num > maior:
                            maior = num
                    except ValueError:
                        continue
    return maior


def criar_sprint(nome, start_date, end_date):
    """Cria uma nova sprint no board."""
    url = f"{BASE_URL}/sprint"
    payload = {
        "name": nome,
        "startDate": start_date,
        "endDate": end_date,
        "originBoardId": int(BOARD_ID),
        "goal": f"Sprint criada automaticamente em {datetime.now(BR_TZ).strftime('%d/%m/%Y')}"
    }
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code in [200, 201]:
        sprint = resp.json()
        print(f"✅ Sprint criada! ID: {sprint['id']} | Nome: {sprint['name']}")
        return sprint
    else:
        print(f"❌ Erro ao criar sprint: {resp.status_code}")
        print(f"Resposta: {resp.text}")
        sys.exit(1)


def mover_issues(issue_keys, sprint_destino_id):
    """Move issues para a sprint de destino."""
    if not issue_keys:
        print("ℹ️ Nenhuma issue para mover.")
        return

    url = f"{BASE_URL}/sprint/{sprint_destino_id}/issue"
    payload = {"issues": issue_keys}
    resp = requests.post(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 204:
        print(f"✅ {len(issue_keys)} issue(s) movida(s) para sprint {sprint_destino_id}")
    else:
        print(f"❌ Erro ao mover issues: {resp.status_code}")
        print(f"Resposta: {resp.text}")


def fechar_sprint(sprint_id, sprint_name):
    """Fecha (conclui) uma sprint."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": sprint_name,
        "state": "closed"
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"✅ Sprint '{sprint_name}' fechada com sucesso!")
        return True
    else:
        print(f"❌ Erro ao fechar sprint: {resp.status_code}")
        print(f"Resposta: {resp.text}")
        return False


def ativar_sprint(sprint_id, sprint_name, start_date, end_date):
    """Ativa uma sprint (muda de future para active)."""
    url = f"{BASE_URL}/sprint/{sprint_id}"
    payload = {
        "name": sprint_name,
        "state": "active",
        "startDate": start_date,
        "endDate": end_date
    }
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"✅ Sprint '{sprint_name}' ativada com sucesso!")
        return True
    else:
        print(f"❌ Erro ao ativar sprint: {resp.status_code}")
        print(f"Resposta: {resp.text}")
        return False


def enviar_notificacao_teams(sprint_fechada_nome, sprint_nova_nome, issues_concluidas, issues_movidas):
    """Envia resumo para o Teams via Adaptive Card (formato obrigatório para webhooks novos)."""
    if not TEAMS_WEBHOOK_URL:
        print("ℹ️ TEAMS_WEBHOOK_URL não configurado. Pulando notificação.")
        return

    # Monta lista de issues concluídas
    lista_concluidas = ""
    if issues_concluidas:
        for issue in issues_concluidas:
            key = issue.get("key", "?")
            summary = issue.get("fields", {}).get("summary", "Sem título")
            lista_concluidas += f"- ✅ {key} — {summary}\\n"
    else:
        lista_concluidas = "- Nenhuma tarefa finalizada nesta sprint\\n"

    # Monta lista de issues movidas
    lista_movidas = ""
    if issues_movidas:
        for issue in issues_movidas:
            key = issue.get("key", "?")
            summary = issue.get("fields", {}).get("summary", "Sem título")
            lista_movidas += f"- 🔄 {key} — {summary}\\n"
    else:
        lista_movidas = "- Nenhuma tarefa transferida\\n"

    # Adaptive Card
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🏁 Sprint Concluída: {sprint_fechada_nome}",
                            "weight": "Bolder",
                            "size": "Large"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"📅 Resumo gerado em {datetime.now(BR_TZ).strftime('%d/%m/%Y às %H:%M')}",
                            "isSubtle": True,
                            "spacing": "None"
                        },
                        {
                            "type": "TextBlock",
                            "text": "─────────────────────────",
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**✅ Tarefas Finalizadas ({len(issues_concluidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_concluidas,
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": f"**🔄 Transferidas → {sprint_nova_nome} ({len(issues_movidas)}):**",
                            "weight": "Bolder",
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": lista_movidas,
                            "wrap": True
                        }
                    ]
                }
            }
        ]
    }

    try:
        resp = requests.post(TEAMS_WEBHOOK_URL, json=card, headers={"Content-Type": "application/json"})
        if resp.status_code in [200, 202]:
            print("✅ Notificação enviada para o Teams!")
        else:
            print(f"⚠️ Falha ao enviar notificação Teams: {resp.status_code}")
            print(f"Resposta: {resp.text}")
    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação Teams: {e}")


# ============================================================
# LÓGICA PRINCIPAL
# ============================================================

def main():
    print("=" * 60)
    print("🚀 AUTOMAÇÃO DE SPRINT - RAJ")
    print(f"📅 Executado em: {datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    # Buscar sprint ativa
    sprint_ativa = get_sprint_ativa()

    if sprint_ativa:
        nome_ativa = sprint_ativa["name"]
        sprint_id = sprint_ativa["id"]
        end_date_str = sprint_ativa.get("endDate", "")

        print(f"\n📌 Sprint ativa: {nome_ativa} (ID: {sprint_id})")
        print(f"📅 Data de término: {end_date_str}")

        # Verificar se a sprint venceu
        if not end_date_str:
            print("⚠️ Sprint ativa sem data de término definida. Nenhuma ação.")
            return

        # Parse da data de fim (formato ISO)
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        hoje = datetime.now(BR_TZ)

        if end_date.date() <= hoje.date():
            print(f"\n⏰ Sprint vencida! ({end_date.strftime('%d/%m/%Y')} <= {hoje.strftime('%d/%m/%Y')})")

            # Buscar issues da sprint ativa
            issues = get_issues_sprint(sprint_id)
            print(f"📋 Total de issues na sprint: {len(issues)}")

            # Separar concluídas vs pendentes
            issues_concluidas = []
            issues_pendentes = []

            for issue in issues:
                status = issue.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
                if status == "done":
                    issues_concluidas.append(issue)
                else:
                    issues_pendentes.append(issue)

            print(f"  ✅ Concluídas: {len(issues_concluidas)}")
            print(f"  🔄 Pendentes (serão movidas): {len(issues_pendentes)}")

            # Determinar próximo número de sprint
            todas_sprints = get_todas_sprints()
            maior_numero = extrair_maior_numero(todas_sprints)
            proximo_numero = maior_numero + 1

            # Calcular datas da nova sprint (7 dias)
            nova_start = hoje.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
            nova_end_date = hoje + timedelta(days=7)
            nova_end = nova_end_date.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

            # Nome da nova sprint
            mes_ano = hoje.strftime("%m/%Y")
            novo_nome = f"Sprint {proximo_numero} - {mes_ano}"

            print(f"\n🆕 Criando: {novo_nome}")
            print(f"   Início: {hoje.strftime('%d/%m/%Y')}")
            print(f"   Fim: {nova_end_date.strftime('%d/%m/%Y')}")

            # 1. Criar nova sprint
            nova_sprint = criar_sprint(novo_nome, nova_start, nova_end)
            nova_sprint_id = nova_sprint["id"]

            # 2. Mover issues pendentes para a nova sprint
            if issues_pendentes:
                issue_keys = [i["key"] for i in issues_pendentes]
                print(f"\n🔄 Movendo issues: {', '.join(issue_keys)}")
                mover_issues(issue_keys, nova_sprint_id)

            # 3. Fechar sprint antiga
            print(f"\n🔒 Fechando sprint: {nome_ativa}")
            fechou = fechar_sprint(sprint_id, nome_ativa)

            # 4. Ativar nova sprint
            if fechou:
                print(f"\n🟢 Ativando sprint: {novo_nome}")
                ativar_sprint(nova_sprint_id, novo_nome, nova_start, nova_end)

                # 5. Enviar notificação para o Teams
                enviar_notificacao_teams(nome_ativa, novo_nome, issues_concluidas, issues_pendentes)
            else:
                print("⚠️ Sprint antiga não foi fechada. Nova sprint criada mas não ativada.")
                print("   Verifique manualmente no Jira.")

        else:
            dias_restantes = (end_date.date() - hoje.date()).days
            print(f"\nℹ️ Sprint ainda não venceu. Vence em {end_date.strftime('%d/%m/%Y')} ({dias_restantes} dia(s) restantes).")
            print("✅ Nenhuma ação necessária.")

    else:
        print("\n⚠️ Nenhuma sprint ativa encontrada no board.")
        print("🆕 Criando nova sprint...")

        # Determinar próximo número
        todas_sprints = get_todas_sprints()
        maior_numero = extrair_maior_numero(todas_sprints)
        proximo_numero = maior_numero + 1

        hoje = datetime.now(BR_TZ)
        nova_start = hoje.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
        nova_end_date = hoje + timedelta(days=7)
        nova_end = nova_end_date.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

        mes_ano = hoje.strftime("%m/%Y")
        novo_nome = f"Sprint {proximo_numero} - {mes_ano}"

        # Criar e ativar
        nova_sprint = criar_sprint(novo_nome, nova_start, nova_end)
        ativar_sprint(nova_sprint["id"], novo_nome, nova_start, nova_end)

    print("\n" + "=" * 60)
    print("✅ AUTOMAÇÃO CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    main()
