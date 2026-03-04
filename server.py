from flask import Flask, jsonify, send_from_directory
import csv, glob, os, re, threading, subprocess, sys
from datetime import datetime

app = Flask(__name__, static_folder='static')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print("=== 서버 버전 확인: importlib 버전 ===")  # 이 줄이 터미널에 보이면 새 버전

crawl_status = {"running": False, "last_run": None, "message": "대기 중"}

# ── 가격 파싱 ──────────────────────────────────────────────────

def parse_thb(s):
    """'฿16,799' → 16799"""
    if not s:
        return 0
    cleaned = re.sub(r'[^0-9]', '', str(s))
    return int(cleaned) if cleaned else 0

def parse_brl(s):
    """'4.29' → 4290, '790' → 790"""
    if not s:
        return 0
    try:
        v = float(str(s).replace(',', '.'))
        return int(v * 1000) if v < 10 else int(v)
    except Exception:
        return 0

# ── 분류 ───────────────────────────────────────────────────────

AREA_MAP_CN = {
    '面部':     '얼굴 전체',
    '中下面部': '중하부 얼굴',
    '单部位':   '단일 부위',
    '私信咨询': '개별 문의',
    '面部+颈部': '얼굴+목',
    '面部含下颌缘': '얼굴+하악연',
}

def classify_brazil_area(service_name: str) -> str:
    s = service_name.upper()
    if any(k in s for k in ['BOLSA OCULAR', 'FOX EYE', 'OLHO', 'PALPEBRA', 'OCULAR']):
        return '눈'
    if any(k in s for k in ['ABDOME', 'ABDOMEN', 'COXA', 'CULOTE', 'BANANINHA',
                              'BRACO', 'GLUTEO', 'COSTAS', 'FLANCO']):
        return '바디'
    return '얼굴'

# ── 데이터 로드 ────────────────────────────────────────────────

def get_thailand_data():
    # 1) 새 크롤러가 생성한 Thailand_YYYYMMDD 폴더 우선
    folders = sorted([
        os.path.join(BASE_DIR, d) for d in os.listdir(BASE_DIR)
        if d.startswith('Thailand_') and os.path.isdir(os.path.join(BASE_DIR, d))
    ])
    if folders:
        folder = folders[-1]
        folder_name = os.path.basename(folder)  # e.g. "Thailand_20260304"
        date_str = folder_name.replace('Thailand_', '')  # "20260304"
        # YYYYMMDD → "2026-03-04" 형식으로
        updated = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str

        rows = []
        csv_files = sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith('.csv')
        ])
        for csv_file in csv_files:
            # 기기명: 파일명에서 날짜 부분 제거 (e.g. "Ultraformer_MPT_20260304.csv" → "Ultraformer MPT")
            base = os.path.splitext(os.path.basename(csv_file))[0]  # "Ultraformer_MPT_20260304"
            device = base.replace(f'_{date_str}', '').replace('_', ' ')  # "Ultraformer MPT"
            with open(csv_file, encoding='utf-8-sig') as fp:
                for row in csv.DictReader(fp):
                    shots = row.get('샷수', '')
                    rows.append({
                        '병원명': row.get('병원명', ''),
                        '시술명': row.get('시술명', ''),
                        '기기명': device,
                        '샷수':   int(shots) if shots and shots.isdigit() else None,
                        '도시':   row.get('도시', ''),
                        '정가':   parse_thb(row.get('정가', '')),
                        '할인가': parse_thb(row.get('할인가', '')),
                    })
        # 날짜별 히스토리: 모든 Thailand_* 폴더에서 기기별 평균가 추출
        history = []
        for hist_folder in folders:
            hname = os.path.basename(hist_folder)
            hds   = hname.replace('Thailand_', '')
            hdate = f"{hds[:4]}-{hds[4:6]}-{hds[6:]}" if len(hds) == 8 else hds
            device_map = {}
            try:
                hfiles = [os.path.join(hist_folder, f) for f in os.listdir(hist_folder) if f.lower().endswith('.csv')]
            except Exception:
                hfiles = []
            for hf in hfiles:
                hbase   = os.path.splitext(os.path.basename(hf))[0]
                hdevice = hbase.replace(f'_{hds}', '').replace('_', ' ')
                hprices = []
                try:
                    with open(hf, encoding='utf-8-sig') as fp:
                        for row in csv.DictReader(fp):
                            p = parse_thb(row.get('할인가', ''))
                            if p > 0:
                                hprices.append(p)
                except Exception:
                    pass
                if hprices:
                    device_map[hdevice] = round(sum(hprices) / len(hprices))
            if device_map:
                history.append({'date': hdate, 'devices': device_map})
        history.sort(key=lambda x: x['date'])

        if rows:
            return {'rows': rows, 'updated': updated, 'history': history}

    # 2) 기존 UF_MPT_Pure_*.csv 폴백
    files = sorted(glob.glob(os.path.join(BASE_DIR, 'UF_MPT_Pure_*.csv')))
    if files:
        rows = []
        with open(files[-1], encoding='utf-8-sig') as fp:
            for row in csv.DictReader(fp):
                shots = row.get('샷수', '')
                rows.append({
                    '병원명': row.get('병원명', ''),
                    '시술명': row.get('시술명', ''),
                    '기기명': 'Ultraformer MPT',
                    '샷수':   int(shots) if shots and shots.isdigit() else None,
                    '도시':   '',
                    '정가':   parse_thb(row.get('정가', '')),
                    '할인가': parse_thb(row.get('할인가', '')),
                })
        return {'rows': rows, 'updated': None, 'history': []}
    return {'rows': [], 'updated': None, 'history': []}

def get_china_data():
    files = sorted(glob.glob(os.path.join(BASE_DIR, 'soyoung_results_*.csv')))
    if not files:
        return []
    rows = []
    with open(files[-1], encoding='utf-8-sig') as fp:
        for row in csv.DictReader(fp):
            area_cn = row.get('area', '')
            rows.append({
                'hospital':       row.get('hospital', ''),
                'area_kr':        AREA_MAP_CN.get(area_cn, area_cn),
                'area_cn':        area_cn,
                'price_online':   int(float(row['price_online']))   if row.get('price_online')   else 0,
                'price_original': int(float(row['price_original'])) if row.get('price_original') else 0,
                'address':        row.get('address', ''),
            })
    return rows

def get_brazil_data():
    files = sorted(glob.glob(os.path.join(BASE_DIR, 'trinks_*.csv')))
    if not files:
        return []
    rows = []
    seen_services = set()
    seen_clinics  = set()
    services = []
    clinics  = []

    with open(files[-1], encoding='utf-8-sig') as fp:
        for row in csv.DictReader(fp):
            sn = row.get('service_name', '')
            h  = row.get('hospital', '')

            if sn and sn not in seen_services:
                seen_services.add(sn)
                services.append({
                    'service_name':  sn,
                    'price':         parse_brl(row.get('price', '')),
                    'duration_min':  int(row['duration_minutes']) if row.get('duration_minutes') else 0,
                    'area':          classify_brazil_area(sn),
                })
            if h and h not in seen_clinics:
                seen_clinics.add(h)
                clinics.append(h)

    return {'services': services, 'clinics': clinics}

# ── 라우트: static 파일 ────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ── 라우트: API ────────────────────────────────────────────────

@app.route('/api/thailand')
def api_thailand():
    return jsonify(get_thailand_data())

@app.route('/api/china')
def api_china():
    return jsonify(get_china_data())

@app.route('/api/brazil')
def api_brazil():
    return jsonify(get_brazil_data())

@app.route('/api/crawl/status')
def api_crawl_status():
    return jsonify(crawl_status)

# ── 크롤링 실행 ────────────────────────────────────────────────

CRAWLERS = [
    ('태국 (GoWabi)',    'thailand_gowabi.py'),
    # ('중국 (소영)',    'china_crawler.py'),   # 파일명 확인 후 주석 해제
    # ('브라질 (Trinks)', 'brazil_crawler.py'), # 파일명 확인 후 주석 해제
]

sys.path.insert(0, BASE_DIR)

def _run_crawlers():
    global crawl_status
    crawl_status.update(running=True, message='크롤링 시작...')
    # Windows cp949 인코딩 문제 해결: UTF-8 강제 설정
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        for country, script in CRAWLERS:
            path = os.path.join(BASE_DIR, script)
            if not os.path.exists(path):
                continue
            crawl_status['message'] = f'{country} 크롤링 중...'
            result = subprocess.run(
                [sys.executable, path],
                cwd=BASE_DIR,
                env=env,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout).strip()
                raise Exception(f'{country} 오류:\n{err}')
        crawl_status.update(
            running=False,
            last_run=datetime.now().strftime('%Y-%m-%d %H:%M'),
            message='완료'
        )
    except Exception as e:
        crawl_status.update(running=False, message=str(e))

@app.route('/api/crawl/log')
def crawl_log():
    log_path = os.path.join(BASE_DIR, 'crawl_error.log')
    if os.path.exists(log_path):
        with open(log_path, encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    return '로그 없음', 200

@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    if crawl_status['running']:
        return jsonify({'status': 'already_running'})
    threading.Thread(target=_run_crawlers, daemon=True).start()
    return jsonify({'status': 'started'})

# ── 실행 ───────────────────────────────────────────────────────

if __name__ == '__main__':
    import webbrowser
    webbrowser.open('http://localhost:5001')
    app.run(host='0.0.0.0', port=5001, debug=False)
