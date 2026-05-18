import streamlit as st
# folium : 지도를 생성하고 데이터를 시각화
import folium
# streamlit_folium : Streamlit 라이브러리 안에서 Folium 지도를 완벽하게 구현하고 양방향으로 소통할 수 있게 도와주는 컴포넌트
from streamlit_folium import st_folium
import requests
import pymysql
from pymysql.cursors import DictCursor
import pandas as pd
from db import DBHandler, get_sqlalchemy_engine 

# 페이지 기본 설정
st.set_page_config(page_title="EV 통합 정보 시스템", layout="wide")

db = DBHandler()
engine = get_sqlalchemy_engine() 

# ----------------------------------------------------------------------
# [데이터] 대한민국 시도별 GeoJSON 데이터 (행정구역 경계선)
#
@st.cache_data
def get_korea_geojson():
    url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    response = requests.get(url)
    return response.json()

try:
    korea_geojson = get_korea_geojson()
except Exception as e:
    st.error("지도를 로드하는 데 실패했습니다. internet 연결을 확인해 주세요.")
    korea_geojson = None


# ----------------------------------------------------------------------
# [DB 연동 핵심] 거꾸로 뒤집힌 DB 구조를 똑바로 재조립하는 핵심 함수
@st.cache_data(ttl=600)  # 10분 간 데이터 캐싱
def load_ev_db_data():
    # 지도 중심 좌표 베이스 프레임
    geo_coords = {
        "지역": ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"],
        "full_name": ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도", "제주특별자치도"],
        "lat": [37.5665, 35.1296, 35.7814, 37.4563, 35.1595, 36.2504, 35.5489, 36.5501, 37.7800, 37.7500, 36.8000, 36.4500, 35.6500, 34.8000, 36.3500, 35.3500, 33.3996],
        "lon": [126.9780, 129.0856, 128.6014, 126.4552, 126.7526, 127.3845, 129.3517, 127.1590, 127.2000, 128.4000, 127.8500, 126.7000, 127.1500, 126.9000, 128.8500, 128.3000, 126.5312]
    }
    df_base = pd.DataFrame(geo_coords)

    try:
        # ----- 1. 전기차 등록 데이터 변환 처리 -----
        # 행에 들어있는 연도 데이터가 '2025'인 로우 전체를 통째로 가져옵니다.
        df_reg_raw = pd.read_sql("SELECT * FROM ev_registration WHERE `지역` = '2025'", engine)
        
        # 가로 세로 반전 제어 (T 사용)
        df_reg_t = df_reg_raw.set_index('지역').T.reset_index()
        df_reg_t.columns = ['지역', '전기차수']
        # '합계' 제외
        df_reg_t = df_reg_t[df_reg_t['지역'] != '합계']

        # ----- 2. 충전소 구축 데이터 변환 처리 -----
        # 충전소 데이터에서 연도가 '2025'인 로우를 가져옵니다.
        df_chg_raw = pd.read_sql("SELECT * FROM ev_charger WHERE `지역` = '2025'", engine)
        df_chg_t = df_chg_raw.set_index('지역').T.reset_index()
        df_chg_t.columns = ['기타컬럼', '충전소수']
        
        # '서울_전체', '경기_전체' 등 '_전체' 컬럼만 필터링하여 지역 매핑 규격화
        df_chg_t = df_chg_t[df_chg_t['기타컬럼'].str.contains('_전체', na=False)]
        df_chg_t['지역'] = df_chg_t['기타컬럼'].str.replace('_전체', '')
        df_chg_final = df_chg_t[['지역', '충전소수']]

        # ----- 3. 마스터 맵 프레임 결합 -----
        df_merged = pd.merge(df_base, df_reg_t, on="지역", how="left")
        df_merged = pd.merge(df_merged, df_chg_final, on="지역", how="left")
        
        # 숫자로 변환하며 결측치 안전 처리
        df_merged["전기차수"] = pd.to_numeric(df_merged["전기차수"], errors='coerce').fillna(0).astype(int)
        df_merged["충전소수"] = pd.to_numeric(df_merged["충전소수"], errors='coerce').fillna(0).astype(int)
        
        # 실시간 점유 비율 연산
        df_merged["전기차비율"] = (df_merged["전기차수"] / df_merged["전기차수"].sum() * 100).round(1)
        df_merged["충전소비율"] = (df_merged["충전소수"] / df_merged["충전소수"].sum() * 100).round(1)
        
        return df_merged

    except Exception as e:
        st.error(f"⚠️ 실시간 DB 변환 연동 실패 (임시 데이터 대체): {e}")
        df_base["전기차수"] = [87135, 50122, 34515, 71284, 16277, 22387, 12485, 6718, 166319, 20398, 25862, 28961, 22764, 33094, 29951, 52778, 47302]
        df_base["충전소수"] = [45210, 18900, 13800, 15400, 8900, 9450, 6100, 4200, 52340, 11200, 12800, 16100, 13100, 14200, 19400, 21050, 22400]
        df_base["전기차비율"] = (df_base["전기차수"] / df_base["전기차수"].sum() * 100).round(1)
        df_base["충전소비율"] = (df_base["충전소수"] / df_base["충전소수"].sum() * 100).round(1)
        return df_base

# 데이터 자동 연동 가동
df_ev = load_ev_db_data()


# [하단 시계열 전용 데이터 복원기]
def load_yearly_trend(table_name):
    try:
        df_raw = pd.read_sql(f"SELECT * FROM {table_name}", engine)
        # 테이블 첫 열 이름이 무조건 '지역'으로 되어 있으므로 이를 '연도'로 의미 변경 명명
        df_raw = df_raw.rename(columns={'지역': '연도'})
        return df_raw
    except Exception as e:
        return None


# ----------------------------------------------------------------------
# 사이드바 및 메뉴 분기
# ----------------------------------------------------------------------
st.sidebar.title("⚡ EV 통합 정보 시스템")
menu = st.sidebar.radio("메뉴를 선택하세요", ["시도별 전기차 현황", "시도별 충전소 현황", "기업 FAQ 조회"])

if (menu == "시도별 전기차 현황" or menu == "시도별 충전소 현황") and korea_geojson:
    
    if menu == "시도별 전기차 현황":
        page_title = "🗺️ 시도별 전기차 등록 현황"
        data_column = "전기차수"
        ratio_column = "전기차비율"
        unit_label = "대"
        db_table_name = "ev_registration"
    else:
        page_title = "🔌 시도별 전기차 충전소(기) 현황"
        data_column = "충전소수"
        ratio_column = "충전소비율"
        unit_label = "기"
        db_table_name = "ev_charger"

    st.title(page_title)
    st.caption("지역 위에 마우스를 올리면 해당 행정구역이 강조되면서 상세 데이터가 나타납니다.")
    
    REGIONAL_DATA = {
        row["full_name"]: {
            "short": row["지역"], "lat": row["lat"], "lon": row["lon"], "value": row[data_column]
        } for _, row in df_ev.iterrows()
    }
    
    # 상단 시각화 레이아웃
    col1, col2 = st.columns([1.1, 1.3])
    
    with col1:
        m = folium.Map(
            location=[36.0, 127.6], zoom_start=7, 
            tiles="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", attr="CartoDB"
        )
        
        for feature in korea_geojson['features']:
            name = feature['properties']['name']
            if name in REGIONAL_DATA:
                feature['properties']['value'] = REGIONAL_DATA[name]['value']
                feature['properties']['short_name'] = REGIONAL_DATA[name]['short']
            else:
                feature['properties']['value'] = 0
                feature['properties']['short_name'] = name

        style_function = lambda x: {
            'fillColor': '#ffffff', 'color': '#ADC6FF', 'weight': 1.5, 'fillOpacity': 1.0
        }
        highlight_function = lambda x: {
            'fillColor': '#5B8FF9', 'color': '#1D4ED8', 'weight': 2.5, 'fillOpacity': 0.85
        }
        
        config_tooltip = folium.features.GeoJsonTooltip(
            fields=['short_name', 'value'], aliases=['지역: ', f'현황({unit_label}): '], localize=True, sticky=False,
            style="font-family: 'Malgun Gothic'; font-size: 13px; color: #333; background: #fff; border: 1px solid #ADC6FF; border-radius: 4px; padding: 8px;"
        )
        
        folium.GeoJson(
            korea_geojson, style_function=style_function, control=False, highlight_function=highlight_function, tooltip=config_tooltip
        ).add_to(m)
        
        for name, info in REGIONAL_DATA.items():
            pin_html = f"""
            <div style="position: relative; background-color: #9BD363; color: white; font-family: 'Malgun Gothic'; font-size: 13px; font-weight: bold; text-align: center; padding: 5px 10px; border-radius: 8px; box-shadow: 1px 2px 4px rgba(0,0,0,0.15); width: fit-content; white-space: nowrap; transform: translate(-50%, -100%);">
                {info['short']}
                <div style="position: absolute; bottom: -6px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 6px solid #9BD363;"></div>
            </div>
            """
            folium.map.Marker(location=[info["lat"], info["lon"]], icon=folium.DivIcon(icon_size=(0, 0), icon_anchor=(0, 0), html=pin_html)).add_to(m)
        
        st_folium(m, width=500, height=550, returned_objects=[])

    with col2:
        st.subheader(f"📊 지역별 {menu.split()[-2]} 시각화")
        chart_df = df_ev.set_index("지역")[[data_column]].rename(columns={data_column: menu.split()[-2]})
        st.bar_chart(chart_df, height=480, use_container_width=True)
        st.caption("<출처: 국토교통부 및 공공데이터포털 통계>")

    # ----------------------------------------------------------------------
    # 하단부: 뒤집혀서 저장된 DB 원본 데이터를 이쁘게 추이 표로 출력
    # ----------------------------------------------------------------------
    st.write("---")
    st.subheader(f"📈 {menu.split()[-2]} 다년도 추이 표 (DB 실시간 데이터)")
    
    df_trend = load_yearly_trend(db_table_name)
    
    if df_trend is not None and not df_trend.empty:
        # 실제 DB 데이터가 있을 때는 불필요한 인덱스(0,1,2..)를 숨기고 화면에 꽉 채워 표만 깔끔하게 출력합니다.
        st.dataframe(df_trend, use_container_width=True, hide_index=True)
    else:
        # DB 연동이 완전히 실패했을 때만 작동하는 백업 영역입니다.
        # 기존에 밖에 나와있던 "st.caption(f'단위 : {unit_label} (%)')" 코드를 이 else 블록 안으로 격리하여 
        # 정상 출력 시에는 화면에 절대 나타나지 않도록 수정했습니다.
        st.caption(f"⚠️ DB 연결 실패로 인한 임시 데이터 표입니다. (단위 : {unit_label})")
        total_val = df_ev[data_column].sum()
        columns_layout = ["연월"] + df_ev["지역"].tolist() + ["계"]
        
        row_data = ["2025 (10월 기준)"]
        for _, row in df_ev.iterrows():
            row_data.append(f"{int(row[data_column]):,}<br>({row[ratio_column]}%)")
        row_data.append(f"**{total_val:,}**")
        
        grid_df = pd.DataFrame([row_data], columns=columns_layout)
        st.write(grid_df.to_html(escape=False, index=False), unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 기업 FAQ 조회 영역 (기존 유지)
# ----------------------------------------------------------------------
elif menu == "기업 FAQ 조회":
    st.title("🏢 기업 및 충전소 FAQ 조회 시스템")
    st.subheader("자주 묻는 질문")
    
    try:
        source_sql = "SELECT DISTINCT source_name FROM faqs WHERE source_name IS NOT NULL"
        sources_data = db.fetch_all(source_sql)
        company_list = [row["source_name"] for row in sources_data]
    except Exception as e:
        company_list = []

    if not company_list:
        company_list = ["무공해차 통합누리집"]

    selected_company = st.selectbox("🏭 조회할 기업(기관)을 선택하세요", company_list)
    search_query = st.text_input("🔍 검색어를 입력하세요 (예: 보조금, 충전기)")
    
    if search_query:
        sql = """
            SELECT category, question, answer 
            FROM faqs 
            WHERE source_name = %s AND (question LIKE %s OR answer LIKE %s)
            ORDER BY id DESC
        """
        params = (selected_company, f"%{search_query}%", f"%{search_query}%")
    else:
        sql = """
            SELECT category, question, answer 
            FROM faqs 
            WHERE source_name = %s 
            ORDER BY id DESC 
            LIMIT 20
        """
        params = (selected_company,)
        
    try:
        faq_list = db.fetch_all(sql, params)
    except Exception as e:
        st.error("데이터베이스 연결에 실패했습니다.")
        faq_list = []

    st.write("---")
    st.markdown(f"📢 **{selected_company}**에서 수집된 FAQ 결과입니다.")
    
    if not faq_list:
        st.info(f"현재 '{selected_company}' 기업에 등록된 FAQ 데이터가 없습니다.")
    else:
        for faq in faq_list:
            category_badge = f"[{faq['category']}] " if faq['category'] else ""
            with st.expander(f"❓ {category_badge}{faq['question']}"):
                st.write(faq["answer"])