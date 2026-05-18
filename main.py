import subprocess
import time
import sys

def main():
    print("🚀 [시스템 가동] EV 통합 정보 플랫폼 및 전체 크롤러 엔진을 시작합니다...")

    # 1. 실행할 크롤러 파일 목록 정의
    crawler_files = ["FAQ.py", "FAQ_hyn.py", "evcar.py"]
    running_processes = []

    # 2. 모든 크롤러 파일을 순회하며 '백그라운드 비동기(Non-Blocking)'로 동시 실행
    for crawler in crawler_files:
        try:
            # Popen을 사용해 메인 코드가 멈추지 않고 즉시 다음 코드로 넘어가게 처리합니다.
            process = subprocess.Popen(
                [sys.executable, crawler],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            running_processes.append((crawler, process))
            print(f"⚡ [백엔드 수집 엔진] '{crawler}' 가 백그라운드에서 가동되었습니다.")
        except Exception as e:
            print(f"❌ [백엔드 에러] '{crawler}' 실행 중 오류 발생: {e}")

    # 3. 크롤러들이 초기 메모리 할당 및 네트워크 자원을 잡을 수 있도록 잠시 대기
    time.sleep(2)

    # 4. 프런트엔드 대시보드(Streamlit) 실행
    print("\n📈 [프런트엔드] Streamlit 대시보드 웹 서버를 구동합니다...")
    try:
        # run()은 대시보드가 완전히 종료될 때까지(사용자가 끌 때까지) 프로세스를 붙잡아둡니다.
        subprocess.run(["streamlit", "run", "app.py"])
    except KeyboardInterrupt:
        print("\n👋 사용자에 의해 시스템 종료 명령(Ctrl+C)이 입력되었습니다.")
    finally:
        print("\n🛑 [시스템 종료 절차] 가동 중인 백그라운드 크롤러 자원을 회수합니다...")
        
        # 5. 대시보드가 꺼지거나 강제 종료되면 백그라운드에서 돌던 모든 크롤러를 안전하게 강제 종료(Kill)
        for crawler_name, process in running_processes:
            # poll()이 None이면 아직 프로그램이 실행 중이라는 의미입니다.
            if process.poll() is None:
                process.terminate()
                print(f"   -> 백그라운드 좀비 프로세스 방지: '{crawler_name}' 종료 완료.")
        
        print("✨ 모든 시스템 자원이 안전하게 해제되었습니다. 프로그램을 종료합니다.")

if __name__ == "__main__":
    main()