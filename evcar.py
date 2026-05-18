"""
전기차 등록현황 + 충전기 구축현황 CSV → MySQL 저장 스크립트

의존성:
  pip install pymysql pandas sqlalchemy
"""

import pandas as pd
from sqlalchemy import create_engine, text

# ── DB 연결 설정 ────────────────────────────────────────────
HOST     = "localhost"
PORT     = 3306
USER     = "student"
PASSWORD = "student80"
DATABASE = "ev_database"

# ── CSV 경로 ────────────────────────────────────────────────
EV_CSV      = r"C:\python_workspace\전기차등록현황_년도별지역별_20~25년.csv"
CHARGER_CSV = r"C:\python_workspace\충전소구축현황_년도별지역별_20~25년.csv"

# ── DB / 테이블 자동 생성 후 저장 ───────────────────────────
def get_engine(with_db: bool = True):
    db = DATABASE if with_db else ""
    url = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{db}?charset=utf8mb4"
    return create_engine(url)


def create_database():
    """ev_project DB가 없으면 자동 생성"""
    engine = get_engine(with_db=False)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` CHARACTER SET utf8mb4;"))
    print(f"[DB] '{DATABASE}' 준비 완료")


def save_to_mysql(csv_path: str, table_name: str):
    """CSV 읽어서 MySQL 테이블에 저장 (기존 테이블 덮어쓰기)"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"년도": str})

    engine = get_engine(with_db=True)
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="replace",   # 테이블 없으면 생성, 있으면 덮어쓰기
        index=False
    )
    print(f"[저장 완료] {table_name} ({len(df)}행 × {len(df.columns)}열)")


def main():
    # 1. DB 생성
    create_database()

    # 2. 전기차 등록현황 저장
    save_to_mysql(EV_CSV, "ev_registration")

    # 3. 충전기 구축현황 저장
    save_to_mysql(CHARGER_CSV, "ev_charger")

    # 4. 저장 확인
    engine = get_engine(with_db=True)
    with engine.connect() as conn:
        for table in ["ev_registration", "ev_charger"]:
            result = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`"))
            count = result.scalar()
            print(f"[확인] {table} → {count}행")

    print("\n✅ MySQL 저장 완료!")
    print(f"   host     : {HOST}")
    print(f"   database : {DATABASE}")
    print(f"   tables   : ev_registration, ev_charger")


if __name__ == "__main__":
    main()