# ReservaSala 🏢 Sala de Agendamento Inteligente

> Sistema web para gestão de reservas de salas — promovendo eficiência operacional e segurança no uso de espaços.

---

## 📌 Visão Geral

**ReservaSala** é uma aplicação projetada para otimizar o agendamento de salas, com foco em evitar conflitos, oferecer transparência de calendário e permitir integrações com agendas externas.  
Ideal para empresas, coworkings ou repartições públicas que precisam gerenciar salas com segurança e visibilidade.

---

## 💼 Problema Resolvido

- Conflitos de horários por múltiplas reservas simultâneas.  
- Falta de visibilidade sobre quais salas estão ocupadas em determinado horário.  
- Dificuldade de integração com calendários externos.  
- Controle de acesso mínimo para modificações (só quem marcou pode deletar ou editar).  
- Falta de informações em tempo real para usuários conectados.

---

## 🔍 Principais Funcionalidades

| Funcionalidade | Descrição |
|---|---|
| Visualização mensal do calendário | Ver eventos/reservas por mês com agendamento visível. |
| Criação de reserva | Definir título, data, horário, e-mail do solicitante. |
| Validação de horário | Evita sobreposições de reservas no mesmo período. |
| Edição/Exclusão protegida | Apenas o criador (via e-mail) pode editar ou excluir. |
| Exportação ICS | Gerar arquivo ICS para importar em Google Calendar, Outlook, etc. |
| Token de segurança para ICS | Proteção extra para acesso ao arquivo de calendário. |
| **Ticker de Notícias em Tempo Real** | Barra fixa inferior que consome o feed RSS da **InfoMoney**, exibindo notícias atualizadas em *scroll* contínuo. |

---

## 🛠️ Tecnologia & Arquitetura

- **Linguagem & Framework Web**: Python + Flask  
- **Banco de dados**: JSON persistente (`events.json`)  
- **Frontend**: HTML5, CSS3 e template dinâmico Jinja2  
- **Feed de Notícias**: Consumo do RSS da [InfoMoney](https://www.infomoney.com.br/feed/) via JavaScript  
- **Dependências**: listadas em `requirements.txt`

---

## ⚙️ Instalação & Setup

Siga estes passos para rodar localmente:

```bash
# 1. Clone o repositório
git clone https://github.com/mildestinos/ReservaSala.git
cd ReservaSala

# 2. (Opcional) Crie um ambiente virtual
python -m venv .venv
# No Linux/macOS:
source .venv/bin/activate
# No Windows:
.venv\Scripts\activate

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure variáveis de ambiente (opcional, para segurança)
# SECRET_KEY para Flask
export SECRET_KEY='uma_chave_secreta'
# Token para acesso ICS (se quiser proteger)
export ICS_TOKEN='seu_token_seguro'

# 5. Execute a aplicação
python app.py
