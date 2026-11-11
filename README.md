# ETF Insight — 무료 공개 웹 분석 데모

**완전 무료로 공개하기 위한 경량 버전**입니다. 유료 PostgreSQL·서버·객체저장소를 요구하지 않습니다.

## GitHub + Streamlit Community Cloud 배포 (무료)

1. [GitHub](https://github.com/new)에서 빈 저장소를 생성합니다. `README` 자동 생성은 선택하지 마세요.
2. 압축을 해제한 후 `app.py`, `etf_engine.py`, `requirements.txt` 3개 파일만 GitHub 저장소에 올립니다. 기존 ETF Insight 원본 ZIP이나 DB 파일을 GitHub에 올리지 마세요.
3. [Streamlit Community Cloud](https://share.streamlit.io/)에 GitHub로 로그인한 다음 **Create app / Deploy a public app**을 선택합니다.
4. 생성한 저장소를 선택하고 **Main file path**를 `app.py`로 지정합니다. 무료 플랜인지 확인한 후 Deploy합니다.
5. 생성된 `https://...streamlit.app` 링크를 공유하면 됩니다. 웹사이트 이용자는 설치할 것이 없습니다.

## 사용하기

- **파일 업로드**: KRX ETF 기본정보 또는 ETF 구성종목 Excel·CSV를 올리면 자동 인식합니다.
- **ETF 검색**: 업로드한 목록 범위에서 검색합니다.
- **실질분석**: 검증한 실제 구성비중으로 최대종목·상위3·상위5·HHI를 계산합니다.
- **유사 ETF 비교**: 후보 검색과, 실제 구성종목을 확보한 ETF 간 중복 비중을 제시합니다.
- **다운로드**: Excel 보고서를 브라우저에서 저장합니다.

## 중요한 제한 및 비용

- 무료 Cloud 서비스는 리소스 제한·절전·재시작 정책이 적용될 수 있습니다. 서비스 제공자의 무료 정책은 변경될 수 있습니다.
- **자료는 개인 브라우저 세션 중 메모리에만 존재**합니다. 세션 종료·서버 재시작 후 유지되지 않습니다. 다른 사람의 데이터와 섞지 않도록 공용 DB를 쓰지 않습니다.
- 기존 ZIP의 93개 ETF 등 실데이터는 이 경량 버전에 포함하지 않았습니다. KRX 파일을 올려야 해당 데이터가 나타납니다.
- DART 자동 연결과 세부 산업·국가 공식 검증은 제공하지 않습니다. 공식 분류를 임의로 생성하지 않습니다.
- 업로드 가능한 데이터만으로 무리하게 정량 유사도 **종합점수를 만들지 않습니다.**
- 회사 내부정보·개인정보·비공개 문서 등은 무료 클라우드에 업로드하지 마세요.
- 설치·배포 전 KRX 및 운용사 데이터 제공조건을 확인해야 합니다. 외부 공개 원본을 서버에 장기 저장하거나 재배포하지 않습니다.
- 무료 호스팅에서 **24시간 무중단 또는 영구저장**을 보장할 수 없습니다.

## 개발자 로컬 실행 (일반 사용자는 불필요)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 테스트

```bash
pip install -r requirements.txt pytest
pytest -q tests
```

기존 기업정보 분석 포함 **전체 기능의 대체물이 아니라**, 비용 0원을 우선하는 실사용 가능 무료 MVP입니다.
