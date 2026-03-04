from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import os
import csv
import re
import json
from datetime import datetime

# ──────────────────────────────────────────────
# ① 시술별 설정 (검색어 / 필터 키워드 / 파일명 prefix)
# ──────────────────────────────────────────────
TREATMENTS = [
    {
        "name":       "Ultraformer_III",
        "search":     "ultraformer III",
        "keywords":   ["Ultraformer III", "Ultraformer3"],
        "exclude":    [" + "],
    },
    {
        "name":       "Ultraformer_MPT",
        "search":     "ultraformer MPT",
        "keywords":   ["Ultraformer MPT", "MPT"],
        "exclude":    [" + "],
    },
    {
        "name":       "Thermage",
        "search":     "thermage",
        "keywords":   ["Thermage"],
        "exclude":    [" + "],
    },
    {
        "name":       "Ulthera",
        "search":     "ulthera",
        "keywords":   ["Ulthera", "Ultherapy"],
        "exclude":    [" + "],
    },
    {
        "name":       "Oligio_X",
        "search":     "oligio x",
        "keywords":   ["Oligio X", "Oligio"],
        "exclude":    [" + "],
    },
    {
        "name":       "Volnewmer",
        "search":     "volnewmer",
        "keywords":   ["Volnewmer"],
        "exclude":    [" + "],
    },
    {
        "name":       "Liftera",
        "search":     "liftera",
        "keywords":   ["Liftera"],
        "exclude":    [" + "],
    },
]

BASE_URL = (
    "https://www.gowabi.com/ko/search"
    "?utf8=%E2%9C%93"
    "&filter%5Bsearch_text%5D={search}"
    "&filter%5Bonly_promotions%5D=false"
    "&filter%5Bsort_by%5D="
)

# ──────────────────────────────────────────────
# 지역명 → 도시 분류 매핑
# ──────────────────────────────────────────────
BANGKOK_AREAS = {
    # 수쿰빗
    "asok", "phrom phong", "thong lo", "thonglor", "ekkamai", "on nut",
    "udom suk", "bang na", "phra khanong", "punnawithi", "khlong tan",
    "khlong tan nuea", "khlong toei", "khlong toei nuea", "phra ram 9",
    # 실롬/사톤
    "silom", "sathon", "sathorn", "sala daeng", "bang rak", "yan nawa",
    "yannawa", "suriya wong", "sam yan",
    # 시암/치담/파야타이
    "siam", "chit lom", "phloen chit", "ratchathewi", "phaya thai",
    "thanon phaya thai", "pathum wan", "pratunam", "rajdamri",
    # 아리/파혼요틴/짜뚜짝/랏프라오
    "ari", "saphan kwai", "phahon yothin", "chatuchak", "lat phrao",
    "ladprao", "ratchadaphisek", "ratchada", "huai khwang", "wang thonglang",
    "chom phon", "anusawari", "anusaori", "sena nikhom", "samsen nok",
    # 북부
    "don mueang", "lak si", "laksi", "bang khen", "thung song hong",
    "bang sue", "tao poon", "pak kret", "mueang nonthaburi",
    # 동부
    "lat krabang", "min buri", "minburi", "hua mak", "khan na yao",
    "prawet", "suan luang", "bang kapi", "phlabphla", "saphansong",
    "chan kasem", "sanambin",
    # 서부/남부
    "bang khae", "bang khae nuea", "nong khang phlu", "bang wa", "bang waek",
    "phasi charoen", "pak khlong phasi charoen", "taling chan", "bangkok noi",
    "arun amarin", "thon buri", "bang kho laem", "thung khru",
    "phutthamonthon", "om noi", "bang khun thian",
    # 강남쪽
    "thawi watthana", "lum phi ni", "lumphini", "lumpini", "din daeng",
    "dusit", "bang ao", "khlong san",
    # 외곽 방콕 생활권
    "bang sue", "bang rak noi", "bang rak phatthana", "bang phli",
    "bang phli yai", "bang phueng", "samrong nuea", "phraeksa",
    "mueang samut sakhon", "bang prok", "don yai hom", "khu khot",
    "rangsit", "khlong nueng", "bueng yitho", "bang yai", "bang kruai",
    "bang bua thong",
}

CHIANGMAI_AREAS = {
    "chiang mai", "chiangmai", "nimman", "nimmanhaemin", "hang dong",
    "mae hia", "san sai", "san sai noi", "suthep", "rim kok",
    "old city", "night bazaar", "kad suan kaew", "saraphi",
}

PHUKET_AREAS = {
    "phuket", "patong", "kata", "karon", "rawai", "chalong",
    "phuket town", "kamala", "surin", "bang tao", "laguna",
    "cherng talay", "thalang", "mai khao",
}

PATTAYA_AREAS = {
    "pattaya", "jomtien", "naklua", "bang lamung", "nong prue",
    "sattahip", "chonburi", "bo win",
}

SAMUI_AREAS = {
    "samui", "koh samui", "ko samui", "chaweng", "lamai",
    "bophut", "maenam",
}

def classify_city(area_text: str) -> str:
    a = area_text.lower().strip()
    if any(k in a for k in BANGKOK_AREAS):
        return "방콕"
    if any(k in a for k in CHIANGMAI_AREAS):
        return "치앙마이"
    if any(k in a for k in PHUKET_AREAS):
        return "푸켓"
    return "기타"


# UUID 패턴 제거 (예: Fa475Dc4 6898 4Bba 84Da 619B5Aa011Be)
_UUID_RE = re.compile(
    r'\s+[0-9A-Fa-f]{8}[\s\-][0-9A-Fa-f]{4}[\s\-][0-9A-Fa-f]{4}[\s\-][0-9A-Fa-f]{4}[\s\-][0-9A-Fa-f]{12}$'
)

def clean_hospital_name(name: str) -> str:
    return _UUID_RE.sub("", name).strip()

# ──────────────────────────────────────────────
# ② 크롤러
# ──────────────────────────────────────────────
class GowabiCrawler:
    def __init__(self, headless=True):
        opts = Options()
        if headless:
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")
        self.driver = webdriver.Chrome(options=opts)

    def scroll_to_bottom(self, url):
        print(f"  📍 로딩 중: {url[:80]}...")
        self.driver.get(url)
        time.sleep(7)

        print("  ⬇️  스크롤 중...")
        last_h = self.driver.execute_script("return document.body.scrollHeight")
        scroll_cnt = 0

        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)
            new_h = self.driver.execute_script("return document.body.scrollHeight")
            scroll_cnt += 1
            if new_h == last_h:
                break
            last_h = new_h

        print(f"  ✅ 스크롤 완료 ({scroll_cnt}회)")

    def extract_raw(self):
        """service_wrapper에서 병원명 / 시술명 / 정가 / 할인가 추출"""
        html  = self.driver.page_source
        soup  = BeautifulSoup(html, "html.parser")
        containers = soup.find_all("div", class_="service_wrapper")
        print(f"  🔍 서비스 컨테이너: {len(containers)}개 발견")

        results = []
        for container in containers:
            try:
                # 시술명
                strong = container.find("strong")
                link   = strong.find("a") if strong else None
                treatment_name = link.get_text(strip=True) if link else ""
                href           = link.get("href", "") if link else ""

                # 병원명 (URL 경로에서 파싱)
                hospital = ""
                m = re.search(r"/provider/([^#?/]+)", href)
                if m:
                    raw_name = m.group(1).replace("-", " ").title()
                    hospital = clean_hospital_name(raw_name)

                # 가격: 정가(line-through) / 할인가
                original_price = ""
                discount_price = ""

                # 정가: del, s, strike, 또는 class에 'original'/'before' 포함
                del_tag = container.find(["del", "s", "strike"])
                if del_tag:
                    original_price = del_tag.get_text(strip=True)

                # 할인가: span.prices 내 첫 번째 a 태그
                price_span = container.find("span", class_="prices")
                if price_span:
                    price_a = price_span.find("a")
                    if price_a:
                        discount_price = price_a.get_text(strip=True)
                    else:
                        discount_price = price_span.get_text(strip=True)

                # 정가 == 할인가인 경우 → 할인 없음, original 비워두기
                if original_price == discount_price:
                    original_price = ""

                if treatment_name and hospital:
                    # h5.grey_text는 service_wrapper 바깥 부모에 있으므로 위로 탐색
                    area_text = ""
                    node = container
                    for _ in range(5):  # 최대 5단계 위로
                        node = node.parent
                        if not node:
                            break
                        area_tag = node.find("h5", class_="grey_text")
                        if area_tag:
                            for img in area_tag.find_all("img"):
                                img.decompose()
                            area_text = area_tag.get_text(strip=True)
                            break

                    results.append({
                        "병원명": hospital,
                        "시술명": treatment_name,
                        "도시":   classify_city(area_text),
                        "정가":   original_price,
                        "할인가": discount_price,
                    })
            except Exception as e:
                pass

        return results

    def crawl(self, search_term):
        url = BASE_URL.format(search=search_term.replace(" ", "%20"))
        self.scroll_to_bottom(url)
        return self.extract_raw()

    def quit(self):
        self.driver.quit()


# ──────────────────────────────────────────────
# ③ Cleanser (시술별 필터링 + 샷수 추출)
# ──────────────────────────────────────────────
def is_pure(treatment_name: str, keywords: list, exclude: list) -> bool:
    name_lower = treatment_name.lower()
    has_keyword = any(k.lower() in name_lower for k in keywords)
    has_exclude = any(e.lower() in name_lower for e in exclude) or "+" in treatment_name
    
    # FREE가 키워드보다 앞에 있으면 → 메인 시술이 따로 있고 울트라포머는 서비스
    if has_keyword and not has_exclude:
        for kw in keywords:
            idx_kw   = name_lower.find(kw.lower())
            idx_free = name_lower.find("free")
            if idx_free != -1 and idx_free < idx_kw:
                return False
    
    return has_keyword and not has_exclude


def extract_shots(treatment_name: str):
    m = re.search(r"(\d+)\s*(?:shots?|lines?|areas?)", treatment_name, re.IGNORECASE)
    return int(m.group(1)) if m else None


def clean_and_save(raw: list, treatment_cfg: dict) -> str:
    """필터링 후 CSV 저장, 파일명 반환"""
    keywords = treatment_cfg["keywords"]
    exclude  = treatment_cfg["exclude"]
    name     = treatment_cfg["name"]

    filtered = []
    for item in raw:
        t = item["시술명"]
        if is_pure(t, keywords, exclude):
            filtered.append({
                "병원명": item["병원명"],
                "시술명": t,
                "샷수":   extract_shots(t),
                "도시":   item.get("도시", ""),
                "정가":   item["정가"],
                "할인가": item["할인가"],
            })

    # 중복 제거 (병원명 + 시술명 기준)
    seen = set()
    unique = []
    for item in filtered:
        key = f"{item['병원명']}|{item['시술명']}"
        if key not in seen:
            seen.add(key)
            unique.append(item)

    print(f"  ✂️  필터링: {len(raw)} → 중복제거 후 {len(unique)}개")

    # 샷수별 분포 출력
    shots_dist = {}
    for item in unique:
        s = item["샷수"]
        shots_dist[s] = shots_dist.get(s, 0) + 1
    for s in sorted([k for k in shots_dist if k is not None]):
        print(f"    {s:>4} 샷: {shots_dist[s]}개")
    if None in shots_dist:
        print(f"    샷수미상: {shots_dist[None]}개")

    # 도시별 분포 출력
    city_dist = {}
    for item in unique:
        c = item["도시"]
        city_dist[c] = city_dist.get(c, 0) + 1
    print(f"  🗺️  도시별 분포:")
    for city, cnt in sorted(city_dist.items(), key=lambda x: -x[1]):
        print(f"    {city}: {cnt}개")

    # 저장 폴더 생성
    ts       = datetime.now().strftime("%Y%m%d")
    folder   = f"Thailand_{ts}"
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"{name}_{ts}.csv")
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["병원명", "시술명", "샷수", "도시", "정가", "할인가"])
        writer.writeheader()
        writer.writerows(unique)

    print(f"  💾 저장 완료: {filename}  ({len(unique)}건)\n")
    return filename


# ──────────────────────────────────────────────
# ④ 메인 실행
# ──────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  Gowabi 통합 크롤러 + Cleanser")
    print("=" * 70 + "\n")

    crawler   = GowabiCrawler(headless=True)   # headless=False 로 바꾸면 브라우저 표시
    saved_files = []

    for cfg in TREATMENTS:
        print(f"{'─'*70}")
        print(f"🚀 [{cfg['name']}] 크롤링 시작")
        print(f"{'─'*70}")

        try:
            raw = crawler.crawl(cfg["search"])
            print(f"  📦 수집된 원본 데이터: {len(raw)}건")
            fname = clean_and_save(raw, cfg)
            saved_files.append(fname)
        except Exception as e:
            print(f"  ❌ 오류 발생: {e}\n")

        # 서버 부담 줄이기 위해 다음 시술 전 잠깐 대기
        time.sleep(3)

    crawler.quit()

    print("=" * 70)
    print("🎉 모든 시술 크롤링 완료!")
    print("=" * 70)
    for f in saved_files:
        print(f"  ✅ {f}")
    print()


if __name__ == "__main__":
    main()