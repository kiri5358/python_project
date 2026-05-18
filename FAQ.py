"""
무공해차 통합누리집 FAQ 크롤러 - Selenium 버전

이유:
- requests로 받은 HTML의 body가 비어 있음
- pnp4web.js 실행 후 브라우저에서 실제 화면이 렌더링되는 구조로 보임
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


FAQ_URL = "https://ev.or.kr/nportal/partcptn/initFaqAction.do"
SOURCE_NAME = "무공해차 통합누리집"
KIA_FAQ_URL = "https://www.kia.com/kr/customer-service/center/faq"
KIA_SOURCE_NAME = "기아 FAQ"

def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_question_hash(source_name: str, question: str) -> str:
    raw = f"{source_name}:{question}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_faq_dict(
    question: str,
    answer: str,
    category: str = "기타",
) -> Dict[str, str]:
    question = clean_text(question)
    answer = clean_text(answer)
    category = clean_text(category) or "기타"

    return {
        "source_name": SOURCE_NAME,
        "source_url": FAQ_URL,
        "category": category,
        "question": question,
        "answer": answer,
        "question_hash": make_question_hash(SOURCE_NAME, question),
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def parse_category_and_question(raw_question: str) -> tuple[str, str]:
    raw_question = clean_text(raw_question)

    match = re.match(r"^\[([^\]]+)\]\s*(.+)$", raw_question)
    if match:
        return clean_text(match.group(1)), clean_text(match.group(2))

    return "기타", raw_question


def create_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Chrome WebDriver 생성

    headless=False:
    - 처음 디버깅할 때 브라우저가 보이게 실행
    - 사이트가 제대로 열리는지 눈으로 확인 가능

    나중에 안정화되면 headless=True로 바꿔도 됨
    """
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ko-KR")

    driver = webdriver.Chrome(options=options)
    return driver


def fetch_faq_page_by_selenium() -> str:
    """
    Selenium으로 페이지 렌더링 후 HTML 가져오기
    """
    driver = create_driver(headless=False)

    try:
        driver.get(FAQ_URL)

        wait = WebDriverWait(driver, 20)

        # body에 실제 텍스트가 생길 때까지 대기
        wait.until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text.strip()) > 0
        )

        # 추가 렌더링 시간
        time.sleep(2)

        html = driver.page_source

        debug_dir = Path(__file__).resolve().parent
        rendered_html_path = debug_dir / "ev_faq_rendered.html"
        rendered_text_path = debug_dir / "ev_faq_rendered_text.txt"

        soup = BeautifulSoup(html, "html.parser")

        rendered_html_path.write_text(html, encoding="utf-8")
        rendered_text_path.write_text(
            soup.get_text("\n", strip=True),
            encoding="utf-8",
        )

        print("렌더링 HTML 저장:", rendered_html_path)
        print("렌더링 TEXT 저장:", rendered_text_path)
        print("렌더링 HTML 길이:", len(html))
        print("렌더링 TEXT 길이:", len(soup.get_text()))

        return html

    finally:
        driver.quit()


def parse_by_table_structure(soup: BeautifulSoup) -> List[Dict[str, str]]:
    faqs: List[Dict[str, str]] = []

    rows = soup.select("table tbody tr, table tr")

    for row in rows:
        cells = [clean_text(td.get_text(" ", strip=True)) for td in row.select("td")]
        cells = [cell for cell in cells if cell]

        if len(cells) < 2:
            continue

        # FAQ 목록형: 번호 / 구분 / 제목
        # 상세 페이지형: 질문 / 답변
        category = "기타"
        question = ""
        answer = ""

        if len(cells) >= 3:
            category = cells[1]
            question = cells[2]
            answer = cells[-1]
        elif len(cells) == 2:
            question = cells[0]
            answer = cells[1]

        parsed_category, parsed_question = parse_category_and_question(question)

        if parsed_category != "기타":
            category = parsed_category

        question = parsed_question

        if len(question) >= 5 and len(answer) >= 5:
            faqs.append(build_faq_dict(question, answer, category))

    return faqs


def parse_by_dl_structure(soup: BeautifulSoup) -> List[Dict[str, str]]:
    faqs: List[Dict[str, str]] = []

    for dl in soup.select("dl"):
        children = [child for child in dl.find_all(["dt", "dd"], recursive=False)]

        current_question = ""

        for child in children:
            text = clean_text(child.get_text(" ", strip=True))

            if not text:
                continue

            if child.name == "dt":
                current_question = text

            elif child.name == "dd" and current_question:
                category, question = parse_category_and_question(current_question)
                answer = text

                if len(question) >= 5 and len(answer) >= 5:
                    faqs.append(build_faq_dict(question, answer, category))

                current_question = ""

    return faqs


def parse_by_common_containers(soup: BeautifulSoup) -> List[Dict[str, str]]:
    faqs: List[Dict[str, str]] = []

    selectors = [
        ".faq li",
        ".faq_list li",
        ".faq-list li",
        ".accordion li",
        ".board_list li",
        ".board-list li",
        ".list li",
        ".faq-item",
        ".item",
    ]

    items = []
    for selector in selectors:
        items.extend(soup.select(selector))

    for item in items:
        question_el = item.select_one(
            ".question, .q, .tit, .title, .subject, .faq-q, button, a"
        )
        answer_el = item.select_one(
            ".answer, .a, .content, .cont, .desc, .reply, .faq-a"
        )

        if not question_el:
            continue

        raw_question = clean_text(question_el.get_text(" ", strip=True))

        if answer_el:
            answer = clean_text(answer_el.get_text(" ", strip=True))
        else:
            answer = clean_text(item.get_text(" ", strip=True).replace(raw_question, "", 1))

        category, question = parse_category_and_question(raw_question)

        if len(question) >= 5 and len(answer) >= 5:
            faqs.append(build_faq_dict(question, answer, category))

    return faqs


def parse_by_text_regex(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    렌더링된 텍스트에서 FAQ 패턴을 최대한 찾아보는 fallback
    """
    faqs: List[Dict[str, str]] = []

    text = clean_text(soup.get_text(" ", strip=True))

    pattern = re.compile(
        r"\[([^\]]{1,30})\]\s*"
        r"(.{5,150}?\?)\s*"
        r"(?:A\.|답변|답)\s*"
        r"(.{10,1200}?)(?=\s*\[[^\]]{1,30}\]\s*.{5,150}?\?\s*(?:A\.|답변|답)|$)",
        re.DOTALL,
    )

    for match in pattern.finditer(text):
        category = clean_text(match.group(1))
        question = clean_text(match.group(2))
        answer = clean_text(match.group(3))

        if len(question) >= 5 and len(answer) >= 5:
            faqs.append(build_faq_dict(question, answer, category))

    return faqs


def remove_duplicates(faqs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    unique_faqs = []
    seen_hashes = set()

    for faq in faqs:
        question_hash = faq["question_hash"]

        if question_hash in seen_hashes:
            continue

        seen_hashes.add(question_hash)
        unique_faqs.append(faq)

    return unique_faqs


def parse_faqs_from_html(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    # 1순위: 무공해차 FAQ 실제 구조
    faqs = parse_by_board_faq_structure(soup)

    # board_faq로 잡히면 table 파싱은 하지 않는다.
    # 이유: 답변 내부의 표를 FAQ로 오인할 수 있기 때문.
    if faqs:
        return remove_duplicates(faqs)

    # fallback들
    faqs = []
    faqs.extend(parse_by_dl_structure(soup))
    faqs.extend(parse_by_common_containers(soup))

    if not faqs:
        faqs.extend(parse_by_text_regex(soup))

    return remove_duplicates(faqs)


def crawl_ev_faqs() -> List[Dict[str, str]]:
    """
    외부에서 호출할 메인 크롤링 함수
    """
    return crawl_all_faq_pages(max_page=4, save_debug=False)

def crawl_faqs() -> List[Dict[str, str]]:
    """
    전체 FAQ 크롤링 통합 함수
    """
    all_faqs: List[Dict[str, str]] = []

    print("[무공해차 FAQ 수집]")
    all_faqs.extend(crawl_ev_faqs())

    print("[기아 FAQ 수집]")
    all_faqs.extend(crawl_kia_faqs())

    return remove_duplicates(all_faqs)

def print_faqs_preview(faqs: List[Dict[str, str]], limit: int = 10) -> None:
    print(f"수집된 FAQ 수: {len(faqs)}")

    for idx, faq in enumerate(faqs[:limit], start=1):
        print("=" * 80)
        print(f"[{idx}] {faq['category']}")
        print(f"Q. {faq['question']}")
        print(f"A. {faq['answer'][:300]}...")
        print(f"출처: {faq['source_url']}")


def parse_by_board_faq_structure(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    무공해차 FAQ 실제 구조 대응

    HTML 구조:
    <div class="board_faq">
        <div class="faq_title">
            <div class="question">Q</div>
            <span class="faq_badge navy_bg">카테고리</span>
            <div class="title">질문</div>
        </div>
        <div class="faq_con">
            <div class="answer">A</div>
            <div>답변 본문</div>
        </div>
    </div>
    """
    faqs: List[Dict[str, str]] = []

    items = soup.select(".board_faq")

    for item in items:
        category_el = item.select_one(".faq_badge")
        question_el = item.select_one(".faq_title .title")
        answer_box = item.select_one(".faq_con")

        if not question_el or not answer_box:
            continue

        category = clean_text(category_el.get_text(" ", strip=True)) if category_el else "기타"
        raw_question = clean_text(question_el.get_text(" ", strip=True))

        # faq_con 안의 'A' 라벨 제거
        answer_label = answer_box.select_one(".answer")
        if answer_label:
            answer_label.extract()

        answer = clean_text(answer_box.get_text(" ", strip=True))

        parsed_category, question = parse_category_and_question(raw_question)

        # 질문 앞의 [안정성], [허가] 같은 값을 세부 카테고리로 쓰고 싶다면 category를 합쳐도 됨
        if parsed_category != "기타":
            category = f"{category} > {parsed_category}"

        if len(question) >= 5 and len(answer) >= 5:
            faqs.append(build_faq_dict(question, answer, category))

    return faqs

def wait_until_faq_loaded(driver: webdriver.Chrome, timeout: int = 40) -> None:
    """
    무공해차 FAQ 목록이 렌더링될 때까지 대기

    기존에는 .board_faq만 기다렸는데,
    사이트 로딩이 느리거나 중간 렌더링 상태일 때 Timeout이 날 수 있어서
    body 텍스트와 FAQ 키워드도 함께 확인한다.
    """
    wait = WebDriverWait(driver, timeout)

    wait.until(
        lambda d: (
            len(d.find_elements(By.CSS_SELECTOR, ".board_faq")) > 0
            or "FAQ" in d.find_element(By.TAG_NAME, "body").text
            or "수소충전소" in d.find_element(By.TAG_NAME, "body").text
            or "완속충전기" in d.find_element(By.TAG_NAME, "body").text
            or "충전소 이용" in d.find_element(By.TAG_NAME, "body").text
        )
    )

    # FAQ 본문 DOM이 늦게 붙는 경우 대비
    time.sleep(2)


def move_to_page(driver: webdriver.Chrome, page_number: int) -> None:
    """
    FAQ 페이지네이션 이동

    page_number:
    - 1이면 현재 첫 페이지 그대로 사용
    - 2 이상이면 페이지 번호 링크 클릭
    """
    if page_number == 1:
        return

    # 페이지 번호 텍스트를 가진 링크 클릭
    page_links = driver.find_elements(By.XPATH, f"//a[normalize-space()='{page_number}']")

    if not page_links:
        raise RuntimeError(f"{page_number}페이지 링크를 찾지 못했습니다.")

    page_links[0].click()

    time.sleep(1.5)
    wait_until_faq_loaded(driver)

def crawl_all_faq_pages(max_page: int = 4, save_debug: bool = False) -> List[Dict[str, str]]:
    """
    무공해차 FAQ 전체 페이지 수집
    """
    driver = create_driver(headless=False)
    all_faqs: List[Dict[str, str]] = []

    try:
        driver.get(FAQ_URL)

        try:
            wait_until_faq_loaded(driver)
        except Exception:
            print("무공해차 FAQ 1차 로딩 실패. 새로고침 후 재시도합니다.")
            driver.refresh()
            time.sleep(3)
            wait_until_faq_loaded(driver)

        for page_number in range(1, max_page + 1):
            print(f"\n[{page_number}페이지 수집 시작]")

            move_to_page(driver, page_number)

            html = driver.page_source
            page_faqs = parse_faqs_from_html(html)

            print(f"{page_number}페이지 FAQ 수: {len(page_faqs)}")

            all_faqs.extend(page_faqs)

            if save_debug:
                debug_dir = Path(__file__).resolve().parent
                rendered_html_path = debug_dir / f"ev_faq_page_{page_number}.html"
                rendered_text_path = debug_dir / f"ev_faq_page_{page_number}.txt"

                soup = BeautifulSoup(html, "html.parser")
                rendered_html_path.write_text(html, encoding="utf-8")
                rendered_text_path.write_text(
                    soup.get_text("\n", strip=True),
                    encoding="utf-8",
                )

        return remove_duplicates(all_faqs)

    finally:
        driver.quit()

def save_faqs_to_db(faqs: List[Dict[str, str]], db_handler) -> int:
    """
    FAQ 데이터를 DB에 저장

    db_handler는 팀의 database/db_handler.py 구조에 맞춰 전달받는 객체로 가정.
    실제 DB 함수 이름은 팀 코드에 맞게 수정 필요.

    반환:
    - 저장 성공/시도 건수
    """
    saved_count = 0

    insert_sql = """
        INSERT INTO faqs (
            source_name,
            source_url,
            category,
            question,
            answer,
            question_hash,
            crawled_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            category = VALUES(category),
            answer = VALUES(answer),
            crawled_at = VALUES(crawled_at)
    """

    for faq in faqs:
        params = (
            faq["source_name"],
            faq["source_url"],
            faq["category"],
            faq["question"],
            faq["answer"],
            faq["question_hash"],
            faq["crawled_at"],
        )

        db_handler.execute_query(insert_sql, params)
        saved_count += 1

    return saved_count

def search_faqs_from_list(
    faqs: List[Dict[str, str]],
    keyword: str = "",
    category: str = "전체",
) -> List[Dict[str, str]]:
    """
    DB 없이도 Streamlit 테스트 가능한 FAQ 검색 함수
    """
    keyword = clean_text(keyword).lower()
    category = clean_text(category)

    results = []

    for faq in faqs:
        faq_category = faq.get("category", "")
        question = faq.get("question", "")
        answer = faq.get("answer", "")

        if category and category != "전체" and not faq_category.startswith(category):
            continue

        if keyword:
            searchable_text = f"{faq_category} {question} {answer}".lower()
            if keyword not in searchable_text:
                continue

        results.append(faq)

    return results

def crawl_kia_faqs() -> List[Dict[str, str]]:
    """
    기아 공식 FAQ 수집
    """
    driver = create_driver(headless=False)

    try:
        driver.get(KIA_FAQ_URL)

        wait = WebDriverWait(driver, 20)
        wait.until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".cmp-accordion__item")) > 0
        )

        time.sleep(1)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        debug_dir = Path(__file__).resolve().parent
        (debug_dir / "kia_faq_rendered.html").write_text(html, encoding="utf-8")
        (debug_dir / "kia_faq_rendered_text.txt").write_text(
            soup.get_text("\n", strip=True),
            encoding="utf-8",
        )

        print("기아 FAQ 렌더링 TEXT 길이:", len(soup.get_text()))

        return parse_kia_faqs_from_html(html)

    finally:
        driver.quit()

def build_faq_dict_by_source(
    source_name: str,
    source_url: str,
    question: str,
    answer: str,
    category: str = "기타",
) -> Dict[str, str]:
    question = clean_text(question)
    answer = clean_text(answer)
    category = clean_text(category) or "기타"

    return {
        "source_name": source_name,
        "source_url": source_url,
        "category": category,
        "question": question,
        "answer": answer,
        "question_hash": make_question_hash(source_name, question),
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def parse_kia_faqs_from_html(html: str) -> List[Dict[str, str]]:
    """
    기아 FAQ HTML 파싱

    실제 FAQ 구조:
    - .cmp-accor-faq 내부
    - .cmp-accordion__item 단위
    - .cmp-accordion__title = 질문
    - .cmp-accordion__panel = 답변

    주의:
    - li를 범용 selector로 잡으면 GNB/메뉴까지 FAQ로 오탐됨
    """
    soup = BeautifulSoup(html, "html.parser")
    faqs: List[Dict[str, str]] = []

    # 기아 FAQ 본문 영역 안의 아코디언만 대상으로 제한
    faq_area = soup.select_one(".cmp-accor-faq")

    if not faq_area:
        return faqs

    items = faq_area.select(".cmp-accordion__item")

    for item in items:
        question_el = item.select_one(".cmp-accordion__title")
        answer_el = item.select_one(".cmp-accordion__panel")

        if not question_el or not answer_el:
            continue

        question = clean_text(question_el.get_text(" ", strip=True))
        answer = clean_text(answer_el.get_text(" ", strip=True))

        # 빈 답변 또는 너무 짧은 값 제외
        if len(question) < 5 or len(answer) < 5:
            continue

        faqs.append(
            build_faq_dict_by_source(
                source_name=KIA_SOURCE_NAME,
                source_url=KIA_FAQ_URL,
                category="기아",
                question=question,
                answer=answer,
            )
        )

    return remove_duplicates(faqs)

if __name__ == "__main__":
    # 1. 🌟 내가 만든 db.py 파일에서 DBHandler 클래스를 가져옵니다.
    from db import DBHandler  
    
    # 2. 🌟 파이썬과 DB를 연결해 주는 객체(db_handler)를 생성합니다.
    db_handler = DBHandler()
    
    # 3. 기아 FAQ 데이터를 수집합니다.
    kia_faqs = crawl_faqs()  
    print(f"📢 기아 FAQ {len(kia_faqs)}건 수집 완료!")
    
    # 4. 🌟 수집된 데이터와 함께 방금 만든 db_handler를 괄호 안에 같이 전달합니다.
    if len(kia_faqs) > 0:
        # ※ 만약 아래처럼 실행했을 때 또 에러가 나면, 순서를 바꿔서 save_faqs_to_db(db_handler, kia_faqs)로 실행해 보세요.
        save_faqs_to_db(kia_faqs, db_handler)  
        print("✅ 기아 FAQ 데이터가 MySQL 'faqs' 테이블에 성공적으로 저장되었습니다!")
    else:
        print("⚠️ 수집된 기아 FAQ 데이터가 없어 DB에 저장하지 않았습니다.")