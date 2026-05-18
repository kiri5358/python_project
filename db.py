# db.py
import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy import create_engine

def get_sqlalchemy_engine():
    # 🌟 팀원분이 evcar.py에 세팅한 DB 접속 정보와 똑같이 맞춰줍니다.
    USER = "student"
    PASSWORD = "student80"
    HOST = "localhost"
    PORT = 3306
    DATABASE = "ev_database"
    
    url = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}?charset=utf8mb4"
    return create_engine(url)

class DBHandler:
    def __init__(self):
        # 아래 정보들을 실제 구축한 MySQL 서버 정보에 맞게 수정하세요.
        self.config = {
            "host": "localhost",
            "user": "student",
            "password": "student80",
            "database": "ev_database",
            "charset": "utf8mb4",
            "cursorclass": DictCursor # 결과값을 딕셔너리 리스트 형태로 받기 위함
        }

    def execute_query(self, sql: str, params: tuple = ()):
        """팀원의 크롤러가 데이터를 저장할 때 사용할 쿼리 실행 함수"""
        connection = pymysql.connect(**self.config)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
            connection.commit()
        finally:
            connection.close()

    def fetch_all(self, sql: str, params: tuple = ()):
        """Streamlit(app.py) 화면에서 데이터를 긁어올 때 사용할 함수"""
        connection = pymysql.connect(**self.config)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            connection.close()