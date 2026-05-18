"""
현대 자동차 FAQ 크롤러 - 수집 건수 0건 해결 및 화면 크기 최적화 버전
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

# ── 1. 타겟 URL 및 소스 이름 정의 ──────────────────────────────────────────
HYUNDAI_FAQ_URL = "https://www.hyundai.com/kr/ko/e/customer/center/faq"
HYUNDAI_SOURCE_NAME = "현대 FAQ"


# ── 2. 유틸리티 공통 함수 ──────────────────────────────────────────────────
def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_question_hash(source_name: str, question: str) -> str:
    raw = f"{source_name}:{question}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_faq_dict_by_source(
    source_name: str,
    source_url: str,
    category: str,
    question: str,
    answer: str,
) -> Dict[str, str]:
    return {
        "source_name": source_name,
        "source_url": source_url,
        "category": category,
        "question": question,
        "answer": answer,
        "question_hash": make_question_hash(source_name, question),
    }


def remove_duplicates(faqs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    unique_faqs = []
    for faq in faqs:
        h = faq["question_hash"]
        if h not in seen:
            seen.add(h)
            unique_faqs.append(faq)
    return unique_faqs


# ── 3. 현대 자동차 다량 FAQ 크롤링 함수 고도화 ───────────────────────────────
def crawl_faqs() -> List[Dict[str, str]]:
    print(f"\n🚀 {HYUNDAI_SOURCE_NAME} 일괄 크롤링 시작...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # 🌟 [해결 포인트 1] 화면 크기를 1920x1080 PC 규격으로 강제 고정합니다.
    # 헤드리스 모드에서 창 크기가 너무 작게 열려 모바일 버전으로 레이아웃이 깨지는 현상을 방지합니다.
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    faqs = []

    try:
        driver.get(HYUNDAI_FAQ_URL)
        time.sleep(7)  # 동적 아코디언 메뉴가 완전히 그려질 때까지 7초 대기

        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")

        # 🌟 [해결 포인트 2] 현대 사이트의 PC버전 및 모바일 버전 태그를 모두 탐색합니다.
        # 기존 셀렉터에 잡히지 않던 개별 리스트 묶음 단위를 정밀 추적합니다.
        items = soup.select(".accordion-item, .faq-item, .accordion-list > li, [class*='accordion'] li, [class*='faq'] li")
        
        # 만약 그래도 안잡힐 경우, 버튼(질문)이 포함된 상위 li 나 div를 직접 강제 수집
        if not items:
            items = soup.find_all(lambda tag: tag.name in ['li', 'div'] and tag.find('button'))

        print(f"🔍 감지된 FAQ 아이템 영역 개수: {len(items)}개")

        for item in items:
            # 질문 영역 추출 (현대 FAQ 내의 버튼이나 타이틀 텍스트 추적)
            question_el = item.select_one(".title, .tit, .question, .accordion-title, button")
            if not question_el:
                continue
                
            question = clean_text(question_el.get_text(" ", strip=True))
            
            # 앞쪽에 붙은 불필요한 공백이나 기호, 숫자 정리
            question = re.sub(r'^[Qq]\.?\s*', '', question)
            question = re.sub(r'^\d+\s*', '', question) 
            
            if len(question) < 4:
                continue

            # 답변 영역 추출
            answer_el = item.select_one(".content, .cont, .answer, .accordion-content, .panel, [class*='content'], [class*='answer']")
            
            if answer_el:
                answer = clean_text(answer_el.get_text(" ", strip=True))
            else:
                # 본문 상자가 따로 분리되지 않은 특이한 아코디언일 경우의 방어 코드
                full_item_text = clean_text(item.get_text(" ", strip=True))
                answer = full_item_text.replace(question, "", 1).strip()

            answer = re.sub(r'^[Aa]\.?\s*', '', answer)

            if len(answer) < 4:
                continue

            faqs.append(
                build_faq_dict_by_source(
                    source_name=HYUNDAI_SOURCE_NAME,
                    source_url=HYUNDAI_FAQ_URL,
                    category="현대",
                    question=question,
                    answer=answer,
                )
            )
            
    except Exception as e:
        print(f"❌ 크롤링 중 에러 발생: {e}")
    finally:
        driver.quit()

    return remove_duplicates(faqs)


# ── 4. 안전한 DB 적재 함수 ──────────────────────────────────────────────────
def save_faqs_to_db(faqs: List[Dict[str, str]], db_handler) -> None:
    if not faqs:
        print("⚠️ 저장할 FAQ 데이터가 존재하지 않습니다.")
        return

    # 🌟 1. SQL 문에 crawled_at 컬럼과 %s를 추가합니다.
    sql = """
        INSERT INTO faqs (source_name, source_url, category, question, answer, question_hash, crawled_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            source_name = VALUES(source_name),
            source_url = VALUES(source_url),
            category = VALUES(category),
            question = VALUES(question),
            answer = VALUES(answer),
            crawled_at = VALUES(crawled_at);
    """
    
    # 🌟 2. 현재 시간을 구합니다. (상단에 datetime이 임포트되어 있어야 합니다)
    from datetime import datetime
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    count = 0
    try:
        if hasattr(db_handler, 'execute'):
            for faq in faqs:
                # 🌟 3. params 맨 마지막에 current_time을 추가해 줍니다.
                params = (
                    faq["source_name"], 
                    faq["source_url"], 
                    faq["category"], 
                    faq["question"], 
                    faq["answer"], 
                    faq["question_hash"],
                    current_time  # 여기에 추가!
                )
                db_handler.execute(sql, params)
                count += 1
        else:
            # (생략) 만약 독립 커넥션을 여는 else 문이 있다면 그 안의 params에도 똑같이 current_time을 추가해야 합니다.
            import pymysql
            conn = pymysql.connect(
                host="localhost", port=3306, user="student", password="student80",
                database="ev_database", charset="utf8mb4"
            )
            with conn.cursor() as cursor:
                for faq in faqs:
                    params = (
                        faq["source_name"], faq["source_url"], faq["category"], 
                        faq["question"], faq["answer"], faq["question_hash"],
                        current_time  # 여기에 추가!
                    )
                    cursor.execute(sql, params)
                    count += 1
            conn.commit()
            conn.close()

        print(f"💾 [DB 성공] 현대 자동차 FAQ {count}건이 실시간으로 DB에 저장되었습니다!")
    except Exception as e:
        print(f"❌ DB 저장 중 에러 발생: {e}")


# ── 5. 메인 실행 제어부 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from db import DBHandler  
    db_handler = DBHandler()
    
    hyn_faqs = crawl_faqs()  
    print(f"📢 현대 FAQ 최종 중복 제거 후 {len(hyn_faqs)}건 추출 성공!")
    
    if len(hyn_faqs) > 0:
        save_faqs_to_db(hyn_faqs, db_handler)