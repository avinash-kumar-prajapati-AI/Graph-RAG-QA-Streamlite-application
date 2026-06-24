"""
db_setup.py — Multi-database initialisation + seeding
"""
from __future__ import annotations
import logging, os, random, sqlite3, uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_DB_DIR = Path(os.getenv("DB_DIR", "./databases"))
_DB_DIR.mkdir(parents=True, exist_ok=True)

def get_db_dir() -> Path: return _DB_DIR
def DB_PATHS_FN(name: str) -> str: return str(_DB_DIR / f"{name}.db")
def db_path(name: str) -> str: return DB_PATHS_FN(name)

def get_conn(name: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(name), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _write_conn(name: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(name), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

SCHEMAS = {
"company": """
CREATE TABLE IF NOT EXISTS departments (dept_id INTEGER PRIMARY KEY AUTOINCREMENT, dept_name TEXT NOT NULL UNIQUE, location TEXT, budget REAL DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS employees (emp_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, role TEXT, salary REAL, dept_id INTEGER REFERENCES departments(dept_id), hire_date TEXT DEFAULT (date('now')), level TEXT CHECK(level IN ('junior','mid','senior','lead','principal')) DEFAULT 'mid', is_active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS projects (proj_id INTEGER PRIMARY KEY AUTOINCREMENT, proj_name TEXT NOT NULL, status TEXT CHECK(status IN ('planning','active','completed','on_hold')) DEFAULT 'planning', budget REAL DEFAULT 0, start_date TEXT, end_date TEXT, dept_id INTEGER REFERENCES departments(dept_id));
CREATE TABLE IF NOT EXISTS assignments (assign_id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id INTEGER REFERENCES employees(emp_id) ON DELETE CASCADE, proj_id INTEGER REFERENCES projects(proj_id) ON DELETE CASCADE, role_on_proj TEXT, hours_per_week INTEGER DEFAULT 10, assigned_on TEXT DEFAULT (date('now')), UNIQUE(emp_id, proj_id));
CREATE TABLE IF NOT EXISTS performance_reviews (review_id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id INTEGER REFERENCES employees(emp_id), year INTEGER, quarter INTEGER CHECK(quarter BETWEEN 1 AND 4), score REAL CHECK(score BETWEEN 1.0 AND 5.0), reviewer TEXT, notes TEXT);
CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(dept_id);
CREATE INDEX IF NOT EXISTS idx_proj_dept ON projects(dept_id);
CREATE INDEX IF NOT EXISTS idx_assign_emp ON assignments(emp_id);
CREATE INDEX IF NOT EXISTS idx_review_emp ON performance_reviews(emp_id, year);
""",
"analytics": """
CREATE TABLE IF NOT EXISTS user_sessions (session_id TEXT PRIMARY KEY, user_id TEXT, started_at TEXT, ended_at TEXT, channel TEXT CHECK(channel IN ('organic','paid','email','social','direct')), country TEXT, device TEXT CHECK(device IN ('desktop','mobile','tablet')));
CREATE TABLE IF NOT EXISTS page_views (view_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT REFERENCES user_sessions(session_id), page TEXT, viewed_at TEXT, time_on_page INTEGER, bounced INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS conversion_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT REFERENCES user_sessions(session_id), event_type TEXT CHECK(event_type IN ('signup','purchase','upgrade','churn','trial_start')), event_at TEXT, revenue REAL DEFAULT 0, product_sku TEXT);
CREATE TABLE IF NOT EXISTS ab_tests (test_id INTEGER PRIMARY KEY AUTOINCREMENT, test_name TEXT, variant TEXT CHECK(variant IN ('control','treatment_a','treatment_b')), session_id TEXT REFERENCES user_sessions(session_id), converted INTEGER DEFAULT 0, revenue REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_sess_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_views_sess ON page_views(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_sess ON conversion_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ab_test ON ab_tests(test_name, variant);
""",
"inventory": """
CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, unit_cost REAL, unit_price REAL, reorder_point INTEGER DEFAULT 50);
CREATE TABLE IF NOT EXISTS warehouses (warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, city TEXT, capacity INTEGER);
CREATE TABLE IF NOT EXISTS stock_levels (stock_id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT REFERENCES products(sku), warehouse_id INTEGER REFERENCES warehouses(warehouse_id), qty_on_hand INTEGER DEFAULT 0, qty_reserved INTEGER DEFAULT 0, last_updated TEXT DEFAULT (datetime('now')), UNIQUE(sku, warehouse_id));
CREATE TABLE IF NOT EXISTS purchase_orders (po_id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT REFERENCES products(sku), warehouse_id INTEGER REFERENCES warehouses(warehouse_id), qty_ordered INTEGER, unit_cost REAL, order_date TEXT, expected_date TEXT, status TEXT CHECK(status IN ('pending','shipped','received','cancelled')) DEFAULT 'pending');
CREATE INDEX IF NOT EXISTS idx_stock_sku ON stock_levels(sku);
CREATE INDEX IF NOT EXISTS idx_po_sku ON purchase_orders(sku);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
"""
}

def _rand_date(s,e):
    a,b=date.fromisoformat(s),date.fromisoformat(e)
    return str(a+timedelta(days=random.randint(0,(b-a).days)))
def _rand_dt(s,e):
    a,b=datetime.fromisoformat(s),datetime.fromisoformat(e)
    return str(a+timedelta(seconds=random.randint(0,int((b-a).total_seconds()))))

def _seed_company(force=False):
    with _write_conn("company") as conn:
        if not force and conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]>0:
            return
        conn.executemany("INSERT OR IGNORE INTO departments (dept_name,location,budget) VALUES (?,?,?)",[
            ("Engineering","New York",2500000),("Data Science","Austin",1800000),
            ("Marketing","San Francisco",1200000),("Product","Seattle",1000000),
            ("HR","Chicago",600000),("Finance","Boston",900000),
            ("DevOps","Remote",1100000),("Security","Washington DC",800000)])
        fnames=["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Henry","Ivy","Jack",
                "Karen","Leo","Maya","Nate","Olivia","Paul","Quinn","Rachel","Sam","Tina",
                "Uma","Victor","Wendy","Xander","Yara","Zoe","Aaron","Beth","Chris","Diana",
                "Ethan","Fiona","Gary","Hannah","Ian","Julia","Kyle","Laura","Mike","Nina"]
        lnames=["Chen","Martinez","Smith","Lee","Johnson","Wang","Kim","Brown","Taylor",
                "Wilson","Davis","Anderson","Thomas","Jackson","White","Harris"]
        droles={1:["Backend Eng","Frontend Eng","Full Stack Eng"],2:["Data Scientist","ML Engineer","Data Analyst"],
                3:["Marketing Manager","Content Lead","SEO Specialist"],4:["Product Manager","UX Researcher"],
                5:["HR Specialist","Recruiter"],6:["Finance Analyst","Controller"],
                7:["DevOps Engineer","SRE","Cloud Architect"],8:["Security Engineer","Pen Tester"]}
        levels=["junior","mid","senior","lead","principal"]
        sbands={"junior":(65000,85000),"mid":(85000,110000),"senior":(110000,145000),"lead":(145000,180000),"principal":(180000,240000)}
        emps=[]
        for i in range(80):
            fn,ln=random.choice(fnames),random.choice(lnames)
            d=random.randint(1,8); l=random.choice(levels)
            emps.append((f"{fn} {ln}",f"{fn.lower()}.{ln.lower()}{i}@corp.com",random.choice(droles[d]),
                         round(random.uniform(*sbands[l]),-2),d,_rand_date("2018-01-01","2024-06-01"),l))
        conn.executemany("INSERT OR IGNORE INTO employees (name,email,role,salary,dept_id,hire_date,level) VALUES (?,?,?,?,?,?,?)",emps)
        conn.executemany("INSERT OR IGNORE INTO projects (proj_name,status,budget,start_date,end_date,dept_id) VALUES (?,?,?,?,?,?)",[
            ("AI Platform v2","active",800000,"2024-01-01","2024-12-31",2),
            ("Website Redesign","active",250000,"2024-03-01","2024-09-30",3),
            ("Cloud Migration","completed",450000,"2023-01-01","2024-01-15",7),
            ("Analytics Dashboard","active",180000,"2024-04-01","2025-01-31",2),
            ("Mobile App v3","active",500000,"2024-02-15","2024-11-30",4),
            ("Zero Trust Security","planning",300000,"2024-08-01","2025-06-30",8),
            ("Data Warehouse","active",650000,"2024-01-15","2024-12-31",2),
            ("HR Portal","on_hold",100000,"2024-05-01",None,5),
            ("API Gateway","completed",200000,"2023-06-01","2024-03-01",1),
            ("Recommendation Engine","active",420000,"2024-03-01","2025-03-01",2)])
        eids=[r[0] for r in conn.execute("SELECT emp_id FROM employees").fetchall()]
        pids=[r[0] for r in conn.execute("SELECT proj_id FROM projects").fetchall()]
        pr=["Tech Lead","Engineer","Analyst","PM","Designer","Architect"]; seen=set()
        for _ in range(130):
            e,p=random.choice(eids),random.choice(pids)
            if (e,p) not in seen:
                seen.add((e,p))
                conn.execute("INSERT OR IGNORE INTO assignments (emp_id,proj_id,role_on_proj,hours_per_week) VALUES (?,?,?,?)",
                             (e,p,random.choice(pr),random.choice([5,10,15,20,25,30,40])))
        for eid in eids:
            for yr in [2022,2023,2024]:
                for q in random.sample([1,2,3,4],k=random.randint(2,4)):
                    conn.execute("INSERT OR IGNORE INTO performance_reviews (emp_id,year,quarter,score,reviewer) VALUES (?,?,?,?,?)",
                                 (eid,yr,q,round(random.uniform(2.5,5.0),1),f"Manager_{random.randint(1,10)}"))
        conn.commit()

def _seed_analytics(force=False):
    with _write_conn("analytics") as conn:
        if not force and conn.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0]>0: return
        channels=["organic","paid","email","social","direct"]
        countries=["US","UK","CA","DE","FR","IN","AU","BR","JP","MX"]
        devices=["desktop","mobile","tablet"]
        pages=["/home","/pricing","/features","/blog","/signup","/dashboard","/docs","/about"]
        et=["signup","purchase","upgrade","trial_start"]; skus=["PRO-001","ENT-001","STR-001","ADD-001"]
        rmap={"signup":0,"trial_start":0,"purchase":99,"upgrade":49}
        tests=["homepage_cta","pricing_page","onboarding_flow"]; vars=["control","treatment_a","treatment_b"]
        sessions=[]
        for _ in range(2000):
            sid=str(uuid.uuid4())[:12]
            start=_rand_dt("2024-01-01 00:00:00","2024-10-01 23:59:59")
            end=str(datetime.fromisoformat(start)+timedelta(minutes=random.randint(1,120)))
            sessions.append((sid,f"user_{random.randint(1,500)}",start,end,
                             random.choice(channels),random.choice(countries),random.choice(devices)))
        conn.executemany("INSERT OR IGNORE INTO user_sessions (session_id,user_id,started_at,ended_at,channel,country,device) VALUES (?,?,?,?,?,?,?)",sessions)
        views=[]
        for sid,*_ in sessions:
            for pg in random.sample(pages,k=random.randint(1,4)):
                views.append((sid,pg,_rand_dt("2024-01-01","2024-10-01"),random.randint(5,600),random.randint(0,1)))
        conn.executemany("INSERT INTO page_views (session_id,page,viewed_at,time_on_page,bounced) VALUES (?,?,?,?,?)",views)
        for sid,*_ in random.sample(sessions,k=400):
            e=random.choice(et); rev=rmap[e]*random.choice([1,12])
            conn.execute("INSERT INTO conversion_events (session_id,event_type,event_at,revenue,product_sku) VALUES (?,?,?,?,?)",
                         (sid,e,_rand_dt("2024-01-01","2024-10-01"),rev,random.choice(skus)))
        for sid,*_ in sessions:
            conn.execute("INSERT INTO ab_tests (test_name,variant,session_id,converted,revenue) VALUES (?,?,?,?,?)",
                         (random.choice(tests),random.choice(vars),sid,random.randint(0,1),round(random.uniform(0,500),2)))
        conn.commit()

def _seed_inventory(force=False):
    with _write_conn("inventory") as conn:
        if not force and conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]>0: return
        conn.executemany("INSERT OR IGNORE INTO products (sku,name,category,unit_cost,unit_price,reorder_point) VALUES (?,?,?,?,?,?)",[
            ("PRO-001","Pro Plan License","Software",20,99,100),("ENT-001","Enterprise License","Software",80,499,50),
            ("STR-001","Starter License","Software",5,29,200),("ADD-001","Analytics Add-on","Software",10,49,75),
            ("HW-001","IoT Sensor Kit","Hardware",45,189,30),("HW-002","Gateway Device","Hardware",120,349,20),
            ("SVC-001","Onboarding Pack","Services",0,999,10),("SVC-002","Training Bundle","Services",0,499,15)])
        conn.executemany("INSERT INTO warehouses (name,city,capacity) VALUES (?,?,?)",[
            ("East Coast DC","New York",5000),("West Coast DC","Los Angeles",6000),
            ("Central Hub","Chicago",8000),("EU Frankfurt","Frankfurt",4000),("APAC Singapore","Singapore",3500)])
        skus=["PRO-001","ENT-001","STR-001","ADD-001","HW-001","HW-002","SVC-001","SVC-002"]
        for wid in range(1,6):
            for sku in skus:
                oh=random.randint(0,500)
                conn.execute("INSERT OR IGNORE INTO stock_levels (sku,warehouse_id,qty_on_hand,qty_reserved) VALUES (?,?,?,?)",
                             (sku,wid,oh,random.randint(0,min(oh,100))))
        for _ in range(200):
            sku=random.choice(skus); od=_rand_date("2023-01-01","2024-10-01")
            ed=str(date.fromisoformat(od)+timedelta(days=random.randint(7,30)))
            conn.execute("INSERT INTO purchase_orders (sku,warehouse_id,qty_ordered,unit_cost,order_date,expected_date,status) VALUES (?,?,?,?,?,?,?)",
                         (sku,random.randint(1,5),random.randint(50,500),round(random.uniform(5,120),2),od,ed,
                          random.choice(["pending","shipped","received","cancelled"])))
        conn.commit()

def init_all(force=False, seed=42):
    random.seed(seed)
    for name, schema in SCHEMAS.items():
        with _write_conn(name) as conn: conn.executescript(schema)
    _seed_company(force); _seed_analytics(force); _seed_inventory(force)

def get_schema_text(db_names=None):
    targets = db_names or list(SCHEMAS.keys())
    parts=[]
    for name in targets:
        try:
            conn=get_conn(name)
            tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            block=[f"=== DATABASE: {name.upper()} ==="]
            for (t,) in tables:
                ddl=conn.execute(f"SELECT sql FROM sqlite_master WHERE name='{t}'").fetchone()
                count=conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                cols=[r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
                block.append(f"-- {t} ({count:,} rows) | columns: {', '.join(cols)}\n{ddl[0]};")
            conn.close(); parts.append("\n\n".join(block))
        except Exception as exc:
            parts.append(f"Error reading {name}: {exc}")
    return "\n\n".join(parts)
