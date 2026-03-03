import streamlit as st
import streamlit.components.v1 as components
import mysql.connector
import html



st.set_page_config(
    page_title="Faglig Tinder – Oversigt",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)


db_user = st.secrets["db_user"]
db_password = st.secrets["db_password"]
db_host = st.secrets["db_host"]
db_name = st.secrets["db_name"]


# Skjul sidebar + fjern margin (kant-til-kant)


# -------------------------
# DB config
# -------------------------
def _get_cfg():
    return {
        "host": db_host,
        "port": 3306,
        "user": db_user,
        "password": db_password,
        "database": db_name,
        "ssl_disabled": False,
    }

st.markdown("""
<style>

/* Skjul topbar */
[data-testid="stHeader"] {
    display: none;
}

/* Skjul footer */
footer {
    visibility: hidden;
}

/* Fjern øverste margin */
.block-container {
    padding-top: 0rem !important;
}

</style>
""", unsafe_allow_html=True)

def _connect():
    cfg = _get_cfg()
    return mysql.connector.connect(
        host=cfg["host"],
        port=int(cfg.get("port", 3306)),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        autocommit=True,
        ssl_disabled=bool(cfg.get("ssl_disabled", True)),
        ssl_ca=cfg.get("ssl_ca"),
    )

def fetch_overview_rows():
    sql = """
    SELECT
        p.id AS problem_id,
        p.tekst AS udfordring,
        COALESCE(
            GROUP_CONCAT(
              DISTINCT u2.navn
              ORDER BY (u2.id = p.userId) DESC, u2.navn
              SEPARATOR ', '
            ),
            ''
        ) AS valgt_af
    FROM Problem p
    LEFT JOIN Vote v ON v.problemId = p.id
    LEFT JOIN Users u2 ON u2.id = v.userId
    GROUP BY p.id, p.tekst, p.userId
    ORDER BY p.id ASC;
    """
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql)
        return cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

# -------------------------
# UI
# -------------------------
st.title("Oversigt: Udfordringer og hvem der har valgt dem")

refresh_seconds = 60
components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

try:
    rows = fetch_overview_rows()
except Exception as e:
    st.error(f"Kunne ikke hente data: {e}")
    st.stop()

# Byg HTML-rækker
rows_html = ""
for r in rows:
    udf = f"{r['problem_id']}. {r['udfordring']}"
    valgt = r["valgt_af"] or ""
    rows_html += (
        "<tr>"
        f"<td class='udf'>{html.escape(udf)}</td>"
        f"<td class='valg'>{html.escape(valgt)}</td>"
        "</tr>"
    )

# Hele tabellen som HTML (stor tekst, 2 kolonner)
table_html = f"""
<style>
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 24px;
    table-layout: fixed;
  }}
  th {{
    text-align: left;
    font-size: 24px;
    padding: 12px 14px;
    border-bottom: 3px solid #ddd;
    background: #f5f5f5;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid #eee;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: anywhere;
  }}
  .udf {{ width: 65%; }}
  .valg {{ width: 35%; }}
</style>

<table>
  <thead>
    <tr>
      <th>Udfordring</th>
      <th>Valgt af</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
"""

# RENDER HTML korrekt (ikke som tekst)
components.html(table_html, height=2200, scrolling=True)

st.caption(f"Opdaterer automatisk hver {refresh_seconds} sek.")