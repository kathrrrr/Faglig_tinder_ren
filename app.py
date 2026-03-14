import streamlit as st
import mysql.connector

import time
st.write("VERSION:", "2026-02-28-TEST")
st.write("FILE:", __file__)
st.write("TIME:", time.time())

db_user = st.secrets["db_user"]
db_password = st.secrets["db_password"]
db_host = st.secrets["db_host"]
db_name = st.secrets["db_name"]

st.set_page_config(page_title="Faglig Tinder", layout="centered")

# -------------------------
# DB config (hardcoded)
# -------------------------
def _get_cfg():
    return {"host": db_host,
        "port": 3306,
        "user": db_user,
        "password": db_password,
        "database": db_name,
        "ssl_disabled": False,
    }

def _connect():
    cfg = _get_cfg()
    kwargs = dict(
        host=cfg["host"],
        port=int(cfg.get("port", 3306)),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        autocommit=True,
    )
    if "ssl_disabled" in cfg:
        kwargs["ssl_disabled"] = bool(cfg["ssl_disabled"])
    if cfg.get("ssl_ca"):
        kwargs["ssl_ca"] = cfg["ssl_ca"]
    return mysql.connector.connect(**kwargs)

def db_fetchone(sql, params=None):
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return cur.fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_fetchall(sql, params=None):
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_execute(sql, params=None):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return cur.lastrowid
    finally:
        try:
            conn.close()
        except Exception:
            pass

# -------------------------
# App helpers
# -------------------------
def ensure_user_strict(navn: str) -> int:
    """Create-only. If name exists, raise ValueError."""
    navn = navn.strip()
    if not navn:
        raise ValueError("Indtast et brugernavn")

    row = db_fetchone("SELECT id FROM Users WHERE navn = %s", (navn,))
    if row:
        raise ValueError("Brugernavnet er optaget. Indtast et andet brugernavn")

    user_id = db_execute("INSERT INTO Users (navn) VALUES (%s)", (navn,))
    return int(user_id)

def list_problems():
    return db_fetchall(
        "SELECT p.id, p.tekst, p.userId, u.navn AS oprettet_af "
        "FROM Problem p LEFT JOIN Users u ON u.id = p.userId "
        "ORDER BY p.id DESC"
    )

def create_problem(user_id: int, tekst: str) -> int:
    tekst = tekst.strip()
    pid = int(db_execute("INSERT INTO Problem (tekst, userId) VALUES (%s, %s)", (tekst, user_id)))
    # auto-vote for own problem
    try:
        db_execute("INSERT INTO Vote (problemId, userId) VALUES (%s, %s)", (pid, user_id))
    except Exception:
        pass
    return pid

def vote_yes(user_id: int, problem_id: int):
    db_execute("INSERT INTO Vote (problemId, userId) VALUES (%s, %s)", (problem_id, user_id))

def vote_remove(user_id: int, problem_id: int):
    db_execute(
        "DELETE FROM Vote WHERE problemId = %s AND userId = %s",
        (problem_id, user_id),
    )
def has_voted_db(user_id: int, problem_id: int) -> bool:
    row = db_fetchone(
        "SELECT 1 FROM Vote WHERE problemId=%s AND userId=%s LIMIT 1",
        (problem_id, user_id),
    )
    return row is not None


def my_votes(user_id: int):
    return db_fetchall(
        "SELECT DISTINCT v.problemId, p.tekst "
        "FROM Vote v JOIN Problem p ON p.id = v.problemId "
        "WHERE v.userId = %s "
        "ORDER BY v.problemId DESC",
        (user_id,),
    )

def count_choices(user_id: int) -> int:
    row = db_fetchone(
        "SELECT COUNT(DISTINCT problemId) AS c FROM Vote WHERE userId = %s",
        (user_id,)
    )
    return int(row["c"] or 0)

def matches_for_user(user_id: int):
    return db_fetchall(
        """
        SELECT
          p.id AS problemId,
          p.tekst AS problemTekst,
          u2.id AS otherUserId,
          u2.navn AS otherNavn
        FROM Vote v_me
        JOIN Problem p ON p.id = v_me.problemId
        JOIN Vote v_other ON v_other.problemId = v_me.problemId AND v_other.userId <> v_me.userId
        JOIN Users u2 ON u2.id = v_other.userId
        WHERE v_me.userId = %s
        ORDER BY p.id DESC, u2.navn
        """,
        (user_id,),
    )
def handle_pending_vote():
    pid = st.session_state.get("busy_vote_pid")
    action = st.session_state.get("busy_vote_action")
    user_id = st.session_state.get("user_id")

    if not pid or not action or not user_id:
        return

    try:
        if action == "yes":
            vote_yes(user_id, pid)
        elif action == "undo":
            vote_remove(user_id, pid)
    finally:
        st.session_state["busy_vote_pid"] = None
        st.session_state["busy_vote_action"] = None
# -------------------------
# UI
# -------------------------
st.title("Faglig Tinder")

st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_name", "")
st.session_state.setdefault("voted_problem_ids", set())  # session-only guard
st.session_state.setdefault("creating_user", False)
st.session_state.setdefault("pending_user_name", "")
st.session_state.setdefault("creating_problem", False)
st.session_state.setdefault("busy_vote_pid", None)
st.session_state.setdefault("busy_vote_action", None)   # "yes" eller "undo"

MAX_CHOICES = 2

tab1, tab2 = st.tabs(["Udfordringer", "Matches"])

# -------------------------
# TAB 1: Udfordringer
# -------------------------
with tab1:
    if not st.session_state["user_id"]:
        st.subheader("Opret brugernavn")
        st.write("Når du er oprettet, bliver du præsenteret for de udfordringer der allerede findes.")

        name = st.text_input("Brugernavn", value=st.session_state["user_name"], placeholder="Fx Kathrine")

        if st.button("Opret", type="primary", disabled=st.session_state["creating_user"]):
            st.session_state["pending_user_name"] = name.strip()
            st.session_state["creating_user"] = True
            st.rerun()

        if st.session_state["creating_user"] and not st.session_state["user_id"]:
            with st.spinner("Opretter bruger..."):
                try:
                    uid = ensure_user_strict(st.session_state["pending_user_name"])
                    st.session_state["user_id"] = uid
                    st.session_state["user_name"] = st.session_state["pending_user_name"]
                    st.session_state["creating_user"] = False
                    st.rerun()
                except ValueError as e:
                    st.session_state["creating_user"] = False
                    st.warning(str(e))
                except Exception as e:
                    st.session_state["creating_user"] = False
                    st.error(f"Kunne ikke oprette bruger: {e}")
    else:
        # --- Status / begrænsning ---
        used = count_choices(st.session_state["user_id"])
        limit_reached = used >= MAX_CHOICES

        with st.sidebar:
            st.subheader("Status")
            st.metric("Valg brugt", f"{used}/{MAX_CHOICES}")
            if limit_reached:
                st.error("Du har nået maksimum.")
            else:
                st.success("Du kan stadig vælge.")

        st.subheader(f"Velkommen {st.session_state['user_name']} ")
        st.write("Klik **Ja** på de udfordringer du gerne vil tale om. Hvis der findes en lignende, så stem ja i stedet for at oprette en ny.")

        if st.session_state["busy_vote_pid"] is not None:
            with st.spinner("Gemmer valg..."):
                try:
                    handle_pending_vote()
                    st.rerun()
                except Exception as e:
                    st.session_state["busy_vote_pid"] = None
                    st.session_state["busy_vote_action"] = None
                    st.error(f"Kunne ikke gemme valg: {e}")

        # --- Liste over udfordringer ---
        try:
            problems = list_problems()
        except Exception as e:
            st.error(f"Kunne ikke hente udfordringer: {e}")
            problems = []

        hide_own = st.checkbox("Skjul mine egne udfordringer", value=True)
        if hide_own:
            problems = [p for p in problems if p.get("userId") != st.session_state["user_id"]]

        if not problems:
            st.info("Ingen udfordringer endnu.")
        else:
                  
            # beregn én gang
            used = count_choices(st.session_state["user_id"])
            limit_reached = used >= MAX_CHOICES

            for p in problems:
                pid = int(p["id"])
                tekst = p["tekst"]
                oprettet_af = p.get("oprettet_af") or "ukendt"

                # check i DB om brugeren har stemt på denne
                has_voted = has_voted_db(st.session_state["user_id"], pid)

                with st.container(border=True):
                    st.markdown(f"**#{pid}** — {tekst}")
                    st.caption(f"Oprettet af: {oprettet_af}")

                    # Hvis stemt: vis Fortryd (altid aktiv)
                    if has_voted:
                        if st.button(
                            "↩️ Fortryd",
                            key=f"undo_{pid}",
                            disabled=(st.session_state["busy_vote_pid"] is not None),
                        ):
                            st.session_state["busy_vote_pid"] = pid
                            st.session_state["busy_vote_action"] = "undo"
                            st.rerun()
                    # Hvis ikke stemt: vis Ja (deaktiveres hvis grænse nået)
                    else:
                        if st.button(
                            "✅ Ja",
                            key=f"yes_{pid}",
                            disabled=(limit_reached or st.session_state["busy_vote_pid"] is not None),
                        ):
                            st.session_state["busy_vote_pid"] = pid
                            st.session_state["busy_vote_action"] = "yes"
                            st.rerun()




        # --- Mine valg ---
        st.divider()
        st.subheader("Mine valg")
        try:
            mv = my_votes(st.session_state["user_id"])
        except Exception as e:
            mv = []
            st.error(f"Kunne ikke hente dine valg: {e}")

        if not mv:
            st.write("Du har ikke stemt ja endnu.")
        else:
            for row in mv:
                st.write(f"• **#{row['problemId']}** — {row['tekst']}")

        # --- Opret egen udfordring nederst ---
        st.divider()
        st.subheader("Kan du ikke finde en lignende? Opret din egen")

        max_len = 280
        tekst = st.text_area("Din udfordring", height=120)

        if st.button("Indsend udfordring", type="primary", disabled=st.session_state["creating_problem"]):
            st.session_state["pending_problem_text"] = tekst.strip()
            st.session_state["creating_problem"] = True
            st.rerun()

        if st.session_state["creating_problem"]:
            with st.spinner("Opretter udfordring..."):
                try:
                    pid = create_problem(st.session_state["user_id"], st.session_state["pending_problem_text"])
                    st.session_state["creating_problem"] = False
                    st.success(f"Udfordring oprettet (#{pid}).")
                    st.rerun()
                except Exception as e:
                    st.session_state["creating_problem"] = False
                    st.error(f"Kunne ikke oprette udfordring: {e}")
# -------------------------
# TAB 2: Matches
# -------------------------
with tab2:
    st.subheader("Matches")
    if not st.session_state["user_id"]:
        st.info("Opret et brugernavn på fanen **Udfordringer** for at se matches.")
    else:
        st.write("Her er personer, der også har stemt ja til de samme udfordringer som dig.")

        try:
            rows = matches_for_user(st.session_state["user_id"])
        except Exception as e:
            rows = []
            st.error(f"Kunne ikke hente matches: {e}")

        if not rows:
            st.info("Ingen matches endnu (eller ingen andre har stemt ja på de samme udfordringer).")
        else:
            by_problem = {}
            for r in rows:
                pid = int(r["problemId"])
                by_problem.setdefault(pid, {"tekst": r["problemTekst"], "people": []})
                by_problem[pid]["people"].append(r["otherNavn"])

            for pid, info in by_problem.items():
                with st.expander(f"#{pid} — {info['tekst']}", expanded=True):
                    uniq_people = sorted(set(info["people"]))
                    st.write("**Andre der har stemt ja:**")
                    st.write(", ".join(uniq_people))